"""Custom exceptions for the BDI reasoning engine.

This module defines domain-agnostic exceptions raised during the BDI
deliberation cycle.  The primary exception, :class:`EpistemicDeadlockError`,
signals that the Teacher LLM has exhausted its retry budget for a particular
intention without producing a valid plan.

Design notes
------------
* The exception carries enough context (the failed DAG, retry count, and
  compressed traces) for the BDI engine to suspend the task and inject
  failure metadata into the agent's epistemic flags.
* No domain-specific types are imported here – only the generic Pydantic
  schemas defined in ``src.core.schemas``.
"""

from __future__ import annotations

from typing import List

from src.core.schemas import IntentionDAG


class EpistemicDeadlockError(Exception):
    """Raised when the BDI engine exceeds its maximum retry budget.

    When the Teacher LLM repeatedly fails to produce an intention DAG that
    passes domain verification, the engine raises this exception so that the
    failing intention can be suspended and a recovery plan can be attempted.

    Attributes
    ----------
    failed_intention : IntentionDAG
        The intention DAG that could not be verified within the retry limit.
    retry_count : int
        How many verification attempts were made before giving up.
    compressed_traces : List[str]
        A list of shortened / compressed error traces from each failed
        verification attempt, useful for injecting into epistemic memory.
    """

    def __init__(
        self,
        failed_intention: IntentionDAG,
        retry_count: int,
        compressed_traces: List[str],
        message: str | None = None,
    ) -> None:
        self.failed_intention: IntentionDAG = failed_intention
        self.retry_count: int = retry_count
        self.compressed_traces: List[str] = compressed_traces

        # Build a human-readable default message when none is provided.
        if message is None:
            message = (
                f"Epistemic deadlock reached for DAG '{failed_intention.dag_id}' "
                f"after {retry_count} retries. "
                f"Compressed traces: {compressed_traces}"
            )

        super().__init__(message)

    def __repr__(self) -> str:  # pragma: no cover – convenience repr
        return (
            f"EpistemicDeadlockError("
            f"dag_id={self.failed_intention.dag_id!r}, "
            f"retry_count={self.retry_count}, "
            f"traces={len(self.compressed_traces)})"
        )
