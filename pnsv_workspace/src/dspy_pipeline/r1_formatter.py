"""R1 Distillation Formatter for Golden Trajectory serialization.

This module converts verified BDI Golden Trajectories into the ``<think>``
tag format expected by DeepSeek-R1-Distill-Qwen-7B for supervised fine-tuning.

Each trajectory is serialized as a single JSON-line in a ``.jsonl`` file with
the following structure::

    {
        "prompt": "<original desire/goal description>",
        "response": "<think>\\n[Belief Updates]:\\n...\\n[Verifier Error ...]\\n...\\n[BDI Reasoning]:\\n...\\n</think>\\n{strict_json_dag_output}"
    }

Key constraints
---------------
* The final JSON DAG output MUST NOT be wrapped in Markdown code fences.
* Each trajectory is one line in the output ``.jsonl`` file.
* This module is domain-agnostic — it works with any GoldenTrajectory
  produced by :class:`~src.core.bdi_engine.BDIEngine`.

Design notes
------------
* ``format_trajectory_for_r1`` converts a single trajectory into a dict.
* ``write_trajectories_to_jsonl`` batch-writes a list of trajectories.
* ``format_and_write_trajectories`` is a convenience function combining both.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.core.schemas import BeliefState, IntentionDAG

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Type alias for the GoldenTrajectory (imported conditionally to avoid
# circular imports — the BDI engine module is heavy).
# ---------------------------------------------------------------------------

try:
    from src.core.bdi_engine import GoldenTrajectory
except ImportError:  # pragma: no cover — only during isolated testing
    GoldenTrajectory = Any  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

THINK_OPEN: str = "<think>"
"""Opening tag for the R1 reasoning block."""

THINK_CLOSE: str = "</think>"
"""Closing tag for the R1 reasoning block."""


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------


def _serialize_belief_state(belief_state: BeliefState) -> str:
    """Serialize a BeliefState into a compact, human-readable string.

    Parameters
    ----------
    belief_state : BeliefState
        The belief state to serialize.

    Returns
    -------
    str
        JSON string representation of the belief state.
    """
    return belief_state.model_dump_json(indent=2)


def _format_error_correction_history(
    history: List[Dict[str, Any]],
) -> str:
    """Format the error correction history into a structured text block.

    Each failed attempt is rendered with its attempt number, error trace,
    and correction hint, providing the student model with a clear picture
    of how the teacher arrived at the correct solution.

    Parameters
    ----------
    history : List[Dict[str, Any]]
        List of dicts with keys ``attempt``, ``error_trace``, and
        ``correction_hint``.

    Returns
    -------
    str
        Formatted multi-line string describing all failed attempts.
        Returns ``"No errors — plan was correct on the first attempt."``
        if the history is empty.
    """
    if not history:
        return "No errors — plan was correct on the first attempt."

    lines: List[str] = []
    for entry in history:
        attempt = entry.get("attempt", "?")
        error_trace = entry.get("error_trace", "N/A")
        correction_hint = entry.get("correction_hint", "N/A")
        lines.append(f"--- Attempt {attempt} ---")
        lines.append(f"Error Trace: {error_trace}")
        lines.append(f"Correction Hint: {correction_hint}")
        lines.append("")  # blank line separator

    return "\n".join(lines).rstrip()


def _format_dag_as_strict_json(intention_dag: IntentionDAG) -> str:
    """Serialize an IntentionDAG as a strict JSON string (no Markdown fences).

    The output is a compact JSON string with no surrounding code blocks,
    as required by the R1 distillation format.

    Parameters
    ----------
    intention_dag : IntentionDAG
        The verified intention DAG.

    Returns
    -------
    str
        Compact JSON string representation of the DAG.
    """
    return intention_dag.model_dump_json()


def _build_belief_update_section(
    belief_before: BeliefState,
    belief_after: BeliefState,
) -> str:
    """Build the ``[Belief Updates]`` section content.

    Describes the state transition from *before* to *after* execution.

    Parameters
    ----------
    belief_before : BeliefState
        The belief state before DAG execution.
    belief_after : BeliefState
        The belief state after DAG execution.

    Returns
    -------
    str
        Multi-line string describing the belief update.
    """
    lines: List[str] = [
        "Before:",
        _serialize_belief_state(belief_before),
        "",
        "After:",
        _serialize_belief_state(belief_after),
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_trajectory_for_r1(
    trajectory: "GoldenTrajectory",
) -> Dict[str, str]:
    """Convert a single GoldenTrajectory into a R1-compatible training record.

    The output dictionary has the following schema::

        {
            "prompt": "<desire description>",
            "response": "<think>\\n...\\n</think>\\n{json_dag}"
        }

    The ``response`` field follows the strict ``<think>`` tag format
    required for DeepSeek-R1 distillation:

    .. code-block:: text

        <think>
        [Belief Updates]:
        {dspy_belief_reasoning}

        [Verifier Error Correction Analysis]:
        {dspy_error_analysis_from_previous_failed_attempts}

        [BDI Reasoning]:
        {dspy_causal_planning_rationale}
        </think>
        {strict_json_dag_output}

    Parameters
    ----------
    trajectory : GoldenTrajectory
        A verified golden trajectory from the BDI engine.

    Returns
    -------
    Dict[str, str]
        A dictionary with ``"prompt"`` and ``"response"`` keys, ready for
        serialization as a single JSONL line.
    """
    # ── Build each section of the <think> block ──

    # 1. Belief Updates section
    belief_updates = _build_belief_update_section(
        belief_before=trajectory.belief_before,
        belief_after=trajectory.belief_after,
    )

    # 2. Verifier Error Correction Analysis section
    error_correction = _format_error_correction_history(
        trajectory.error_correction_history,
    )

    # 3. BDI Reasoning section (from the Teacher LLM's chain-of-thought)
    bdi_reasoning = trajectory.reasoning if trajectory.reasoning else "N/A"

    # ── Assemble the <think> block ──
    think_block = (
        f"{THINK_OPEN}\n"
        f"[Belief Updates]:\n"
        f"{belief_updates}\n"
        f"\n"
        f"[Verifier Error Correction Analysis]:\n"
        f"{error_correction}\n"
        f"\n"
        f"[BDI Reasoning]:\n"
        f"{bdi_reasoning}\n"
        f"{THINK_CLOSE}"
    )

    # ── Strict JSON DAG output (no Markdown fences!) ──
    strict_json_dag = _format_dag_as_strict_json(trajectory.intention_dag)

    # ── Combine into final response ──
    response = f"{think_block}\n{strict_json_dag}"

    # ── Build the prompt from the desire ──
    prompt = json.dumps(trajectory.desire, ensure_ascii=False)

    return {
        "prompt": prompt,
        "response": response,
    }


def write_trajectories_to_jsonl(
    records: List[Dict[str, str]],
    output_path: Union[str, Path],
    *,
    append: bool = False,
) -> Path:
    """Write a list of R1-formatted records to a ``.jsonl`` file.

    Each record is serialized as a single JSON line.

    Parameters
    ----------
    records : List[Dict[str, str]]
        List of dicts with ``"prompt"`` and ``"response"`` keys, as returned
        by :func:`format_trajectory_for_r1`.
    output_path : str | Path
        Path to the output ``.jsonl`` file.
    append : bool, optional
        If ``True``, append to an existing file instead of overwriting.
        Defaults to ``False``.

    Returns
    -------
    Path
        The resolved output path.

    Raises
    ------
    ValueError
        If *records* is empty.
    """
    if not records:
        raise ValueError("Cannot write an empty list of records to JSONL.")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if append else "w"
    with open(output_path, mode, encoding="utf-8") as fh:
        for record in records:
            line = json.dumps(record, ensure_ascii=False)
            fh.write(line + "\n")

    logger.info(
        "Wrote %d trajectory record(s) to %s (mode=%s).",
        len(records),
        output_path,
        mode,
    )
    return output_path


def format_and_write_trajectories(
    trajectories: List["GoldenTrajectory"],
    output_path: Union[str, Path],
    *,
    append: bool = False,
) -> Path:
    """Convenience function: format multiple trajectories and write to JSONL.

    This is the primary entry point for batch-converting BDI engine outputs
    into R1 distillation training data.

    Parameters
    ----------
    trajectories : List[GoldenTrajectory]
        List of verified golden trajectories from the BDI engine.
    output_path : str | Path
        Path to the output ``.jsonl`` file.
    append : bool, optional
        If ``True``, append to an existing file.  Defaults to ``False``.

    Returns
    -------
    Path
        The resolved output path.

    Raises
    ------
    ValueError
        If *trajectories* is empty.

    Example
    -------
    >>> from src.core.bdi_engine import BDIEngine
    >>> engine = BDIEngine(verifier=my_verifier, teacher=my_teacher)
    >>> engine.add_desire({"goal": "stack(A, B)"})
    >>> golden = engine.run()
    >>> from src.dspy_pipeline.r1_formatter import format_and_write_trajectories
    >>> format_and_write_trajectories(golden, "output/training_data.jsonl")
    """
    if not trajectories:
        raise ValueError(
            "Cannot format an empty list of trajectories. "
            "Ensure the BDI engine produced at least one golden trajectory."
        )

    records: List[Dict[str, str]] = []
    for i, traj in enumerate(trajectories):
        try:
            record = format_trajectory_for_r1(traj)
            records.append(record)
        except Exception:
            logger.exception(
                "Failed to format trajectory %d; skipping.", i
            )

    if not records:
        raise ValueError(
            "All trajectories failed to format. "
            "Check the logs for details on individual failures."
        )

    return write_trajectories_to_jsonl(
        records, output_path, append=append
    )
