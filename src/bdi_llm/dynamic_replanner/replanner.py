import os
import logging
from typing import Dict, List, Optional
from openai import OpenAI

from src.bdi_llm.config import Config
from src.bdi_llm.schemas import BDIPlan
from src.bdi_llm.dynamic_replanner.executor import ExecutionResult


logger = logging.getLogger(__name__)


class DynamicReplanner:
    """
    Handles dynamic replanning (repair) by sending execution feedback
    to an LLM to generate a recovery plan. Utilizes explicit Context Cache 
    where supported (e.g. qwen3.5-plus).
    """

    def __init__(self, model_name: str = None, max_retries: int = 3):
        # We explicitly want to use a model that supports caching.
        if model_name is None:
            model_name = Config.MODEL_NAME
        self.model_name = model_name
        self.max_retries = max_retries
        
        # Use Config for API key and base URL so it works with both
        # DashScope and standard OpenAI environments
        api_key = Config.DASHSCOPE_API_KEY or Config.OPENAI_API_KEY
        base_url = Config.OPENAI_API_BASE or 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    def generate_recovery_plan(
        self, 
        beliefs: str, 
        desire: str, 
        execution_result: ExecutionResult
    ) -> Optional[BDIPlan]:
        """
        Constructs a cached prompt containing the original context + the new failure 
        feedback, and requests a recovery plan.
        """
        
        # 1. System Prompt (Cacheable)
        system_prompt = """You are a highly capable BDI (Belief-Desire-Intention) agent.
Your task is to dynamically REPLAN an operation. You previously made a plan, but it failed during execution.
You must analyze the state changes from the actions that *did* succeed, understand why the failed action was blocked, and generate a continuous JSON DAG plan of the REMAINING actions needed to achieve the goal."""

        # 2. Environment Context (Beliefs & Desire) - Cacheable
        # We attach the 'cache_control' to the final message of the cacheable prefix
        environment_context = f"{beliefs}\n\n{desire}"

        # 3. Execution Feedback (Dynamic part, not cached)
        executed_str = "None"
        if execution_result.executed_actions:
            executed_str = "\n".join(f"{i+1}. {a}" for i, a in enumerate(execution_result.executed_actions))
            
        failure_reasons_str = "None provided"
        if execution_result.failure_reason:
            failure_reasons_str = "\n".join(f"- {r}" for r in execution_result.failure_reason)

        feedback_prompt = f"""
=== EXECUTION FEEDBACK ===
Here is the execution history. Update your mental state by applying these actions to the initial state sequentially.

Successfully executed actions:
{executed_str}

Then, you attempted this action:
FAILED ACTION: {execution_result.failed_action}

But it failed due to the following constraint violations:
{failure_reasons_str}

=== YOUR TASK ===
1. Analyze your true CURRENT STATE (Initial State + Successful Actions).
2. Note the failure reason for '{execution_result.failed_action}' to avoid repeating the exact same mistake or expecting an invalid precondition.
3. Generate a BDI JSON DAG plan for the REMAINING actions required to reach the goal from the CURRENT STATE. DO NOT include the already successful actions in your new plan. Focus only on what must be done next.

Output ONLY a valid JSON string (matching the BDIPlan schema: {{"goal_description": "...", "nodes": [...], "edges": [...]}}). Do not include markdown formatting or extra text.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            # Add explicit cache_control if the model supports it. 
            # In OpenAI compatible API for Dashscope, we just pass the standard format.
            {
                "role": "user", 
                "content": environment_context,
            },
            {"role": "user", "content": feedback_prompt}
        ]

        # In qwen3.5-plus, to use explicit cache, we actually need to mark the final message 
        # of the prefix we want to cache. For OpenAI-compatible API on dashscope, the current standard 
        # is sometimes not purely OpenAI standard dictionary. 
        # But we will rely on implicit cache or session cache if explicit fails, 
        # so we will use the safest standard structure.

        for attempt in range(self.max_retries):
            try:
                # Add 'enable_thinking' if it's a model that supports it
                extra_body = {}
                if "thinking" in self.model_name or "plus" in self.model_name:
                    extra_body["enable_thinking"] = True

                # To use Session Cache, we add the header (optional, but good for DashScope)
                extra_headers = {"x-dashscope-session-cache": "enable"}

                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=0.3, # Low temp for planning
                    max_tokens=2048,
                    extra_body=extra_body,
                    extra_headers=extra_headers
                )

                content = response.choices[0].message.content.strip()

                # Delegate all JSON parsing + field normalisation to BDIPlan
                plan = BDIPlan.from_llm_text(content)
                if plan is not None:
                    return plan
                logger.warning(f"Replanning attempt {attempt+1}: from_llm_text returned None")

            except Exception as e:
                logger.warning(f"Replanning attempt {attempt+1} failed: {e}")
        
        return None
