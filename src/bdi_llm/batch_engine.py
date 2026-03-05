"""
Batch Engine for DashScope-compatible Batch Inference API.

Provides utilities to:
1. Generate JSONL request files for batch submission
2. Upload, submit, and poll batch jobs
3. Parse results back into BDIPlan objects

Usage:
    engine = BatchEngine()
    batch_id = engine.submit(requests)
    results = engine.wait_and_download(batch_id)

Author: BDI-LLM Research
"""

import os
import json
import time
import tempfile
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from src.bdi_llm.config import Config
from src.bdi_llm.schemas import BDIPlan, ActionNode, DependencyEdge, parse_plan_from_text  # noqa: F401 – re-export

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ #
# Prompt Builders (shared between initial generation and replanning)
# ------------------------------------------------------------------ #

INITIAL_PLAN_SYSTEM_PROMPT = """You are a BDI (Belief-Desire-Intention) planning agent.
Given an environment description (beliefs) and a goal (desire), generate a complete plan
as a JSON DAG with nodes (actions) and edges (dependencies).

Output ONLY a valid JSON object matching this schema:
{"goal_description": "...", "nodes": [{"id": "s1", "action_type": "...", "params": {...}, "description": "..."}], "edges": [{"source": "s1", "target": "s2", "relationship": "depends_on"}]}

Do not include markdown formatting or extra text."""

REPLAN_SYSTEM_PROMPT = """You are a highly capable BDI (Belief-Desire-Intention) agent.
Your task is to dynamically REPLAN an operation. You previously made a plan, but it failed during execution.
You must analyze the state changes from the actions that *did* succeed, understand why the failed action was blocked, and generate a continuous JSON DAG plan of the REMAINING actions needed to achieve the goal."""


def build_initial_plan_messages(beliefs: str, desire: str) -> List[Dict[str, str]]:
    """Build chat messages for initial plan generation."""
    return [
        {"role": "system", "content": INITIAL_PLAN_SYSTEM_PROMPT},
        {"role": "user", "content": f"{beliefs}\n\n{desire}"},
    ]


def build_replan_messages(
    beliefs: str,
    desire: str,
    executed_actions: List[str],
    failed_action: str,
    failure_reasons: List[str],
) -> List[Dict[str, str]]:
    """Build chat messages for recovery plan generation."""
    executed_str = "None"
    if executed_actions:
        executed_str = "\n".join(f"{i+1}. {a}" for i, a in enumerate(executed_actions))

    failure_reasons_str = "None provided"
    if failure_reasons:
        failure_reasons_str = "\n".join(f"- {r}" for r in failure_reasons)

    feedback = f"""
=== EXECUTION FEEDBACK ===
Successfully executed actions:
{executed_str}

FAILED ACTION: {failed_action}

Constraint violations:
{failure_reasons_str}

=== YOUR TASK ===
1. Analyze your true CURRENT STATE (Initial State + Successful Actions).
2. Avoid repeating the same mistake for '{failed_action}'.
3. Generate a BDI JSON DAG plan for the REMAINING actions to reach the goal from CURRENT STATE.

Output ONLY valid JSON ({{"goal_description": "...", "nodes": [...], "edges": [...]}}).
"""
    return [
        {"role": "system", "content": REPLAN_SYSTEM_PROMPT},
        {"role": "user", "content": f"{beliefs}\n\n{desire}"},
        {"role": "user", "content": feedback},
    ]


# ------------------------------------------------------------------ #
# Batch Engine
# ------------------------------------------------------------------ #

class BatchEngine:
    """
    DashScope Batch API wrapper using OpenAI-compatible interface.

    Workflow:
        1. Build a list of BatchRequest dicts
        2. Call submit() to upload JSONL + create batch job
        3. Call wait_and_download() to poll until done and get results
    """

    def __init__(
        self,
        model: str = None,
        base_url: str = None,
        enable_thinking: bool = True,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        poll_interval: int = 15,
    ):
        self.model = model or Config.MODEL_NAME
        self.enable_thinking = enable_thinking
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.poll_interval = poll_interval

        _base_url = base_url or Config.OPENAI_API_BASE or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.client = OpenAI(
            api_key=Config.DASHSCOPE_API_KEY,
            base_url=_base_url,
        )

    def build_jsonl_line(
        self, custom_id: str, messages: List[Dict[str, str]]
    ) -> str:
        """Build a single JSONL line for batch submission."""
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.enable_thinking:
            body["enable_thinking"] = True

        line = {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": body,
        }
        return json.dumps(line, ensure_ascii=False)

    def submit(
        self,
        requests: List[Tuple[str, List[Dict[str, str]]]],
        description: str = "BDI Batch",
    ) -> str:
        """
        Submit a batch of requests.

        Args:
            requests: List of (custom_id, messages) tuples
            description: Job description for logging

        Returns:
            batch_id
        """
        # Write JSONL to temp file
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        try:
            for custom_id, messages in requests:
                tmp.write(self.build_jsonl_line(custom_id, messages) + "\n")
            tmp.close()

            # Upload
            logger.info(f"Uploading {len(requests)} requests...")
            file_obj = self.client.files.create(
                file=Path(tmp.name), purpose="batch"
            )
            logger.info(f"File uploaded: {file_obj.id}")

            # Create batch
            batch = self.client.batches.create(
                input_file_id=file_obj.id,
                endpoint="/v1/chat/completions",
                completion_window="24h",
            )
            logger.info(f"Batch created: {batch.id} ({description})")
            return batch.id

        finally:
            os.unlink(tmp.name)

    def wait_and_download(
        self, batch_id: str, timeout: int = 3600
    ) -> Dict[str, str]:
        """
        Poll batch status and download results.

        Returns:
            Dict mapping custom_id → LLM response text content
        """
        start = time.time()
        while time.time() - start < timeout:
            batch = self.client.batches.retrieve(batch_id)
            status = batch.status
            logger.info(f"Batch {batch_id}: {status}")

            if status == "completed":
                return self._download_results(batch.output_file_id)
            elif status in ("failed", "expired", "cancelled"):
                error_msg = f"Batch {batch_id} {status}"
                if hasattr(batch, "errors") and batch.errors:
                    error_msg += f": {batch.errors}"
                raise RuntimeError(error_msg)

            time.sleep(self.poll_interval)

        raise TimeoutError(f"Batch {batch_id} timed out after {timeout}s")

    def _download_results(self, output_file_id: str) -> Dict[str, str]:
        """Download and parse batch result file."""
        content = self.client.files.content(output_file_id)
        results = {}

        for line in content.text.strip().split("\n"):
            if not line.strip():
                continue
            row = json.loads(line)
            custom_id = row["custom_id"]
            response_body = row.get("response", {}).get("body", {})
            choices = response_body.get("choices", [])
            if choices:
                msg_content = choices[0].get("message", {}).get("content", "")
                results[custom_id] = msg_content
            else:
                results[custom_id] = ""

        return results
