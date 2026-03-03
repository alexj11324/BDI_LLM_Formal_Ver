"""BDI Engine with dependency-injected verification for domain-agnostic reasoning.

This module implements the core Belief-Desire-Intention (BDI) deliberation
cycle.  The engine is **domain-agnostic**: it depends only on the abstract
:class:`~src.core.verification_bus.BaseDomainVerifier` interface and on the
generic Pydantic schemas defined in :mod:`src.core.schemas`.

Key responsibilities
--------------------
* Maintain a goal queue (desires) and a mutable :class:`BeliefState`.
* Prompt a **Teacher LLM** (DSPy module) to generate an
  :class:`IntentionDAG` for each desire.
* Submit the candidate DAG to the injected verifier (deep-copy semantics).
* On verification success: commit belief-state updates and log the Golden
  Trajectory.
* On failure: inject error traces / correction hints into the LLM context
  and retry (up to ``MAX_RETRIES``).
* On repeated failure: raise :class:`EpistemicDeadlockError`, suspend the
  intention, compress traces into epistemic memory, and invoke recovery.

Design constraints
------------------
* **Zero Domain Leakage** – This module MUST NOT import ``pytest``, ``ast``,
  ``pddl``, or any other domain-specific library.
* **State Immutability** – Verifiers always receive a deep copy of
  ``BeliefState``; the canonical state is only updated on successful
  verification.
* **Strategy Pattern** – All domain logic lives in ``src/plugins/``.  The
  engine interacts with verifiers exclusively through
  :class:`BaseDomainVerifier`.
"""

from __future__ import annotations

import copy
import json
import logging
import re
import uuid
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from src.core.exceptions import EpistemicDeadlockError
from src.core.schemas import BeliefState, IntentionDAG, IntentionNode
from src.core.verification_bus import BaseDomainVerifier

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RETRIES: int = 3
"""Default maximum number of verification retries before epistemic deadlock."""


# ---------------------------------------------------------------------------
# DSPy Teacher Protocol
# ---------------------------------------------------------------------------

class TeacherModule(Protocol):
    """Structural sub-typing protocol for the DSPy teacher module.

    Any object that exposes a ``__call__`` accepting keyword arguments and
    returning an object with a ``.reasoning`` and ``.intention_dag_json``
    attribute satisfies this protocol.  This keeps the BDI engine decoupled
    from the DSPy library itself.
    """

    def __call__(self, **kwargs: Any) -> Any:  # noqa: D401
        """Invoke the teacher module with keyword arguments."""
        ...


# ---------------------------------------------------------------------------
# Golden Trajectory Record
# ---------------------------------------------------------------------------

class GoldenTrajectory:
    """Lightweight container for a single successful BDI reasoning trace.

    Attributes
    ----------
    desire : Dict[str, Any]
        The goal / desire that was resolved.
    intention_dag : IntentionDAG
        The verified intention DAG that resolved the desire.
    belief_before : BeliefState
        Snapshot of the belief state *before* execution.
    belief_after : BeliefState
        Snapshot of the belief state *after* execution.
    reasoning : str
        The Teacher LLM's reasoning chain.
    error_correction_history : List[Dict[str, Any]]
        History of failed attempts (error traces + correction hints) leading
        up to the successful plan.
    """

    __slots__ = (
        "desire",
        "intention_dag",
        "belief_before",
        "belief_after",
        "reasoning",
        "error_correction_history",
    )

    def __init__(
        self,
        desire: Dict[str, Any],
        intention_dag: IntentionDAG,
        belief_before: BeliefState,
        belief_after: BeliefState,
        reasoning: str,
        error_correction_history: List[Dict[str, Any]],
    ) -> None:
        self.desire = desire
        self.intention_dag = intention_dag
        self.belief_before = belief_before
        self.belief_after = belief_after
        self.reasoning = reasoning
        self.error_correction_history = error_correction_history


# ---------------------------------------------------------------------------
# BDI Engine
# ---------------------------------------------------------------------------

class BDIEngine:
    """Domain-agnostic BDI deliberation engine.

    The engine orchestrates the standard BDI cycle – deliberate, plan,
    verify, execute – while remaining completely domain-agnostic.  Domain
    logic is injected at construction time via *verifier* and *teacher*
    arguments (Strategy / Dependency Injection pattern).

    Parameters
    ----------
    verifier : BaseDomainVerifier
        A concrete domain verifier that validates intention DAGs against the
        current belief state.
    teacher : TeacherModule
        A DSPy module (or any callable satisfying :class:`TeacherModule`)
        that generates :class:`IntentionDAG` JSON from a belief state and a
        desire.
    max_retries : int, optional
        Maximum verification attempts before raising
        :class:`EpistemicDeadlockError`.  Defaults to :data:`MAX_RETRIES`.
    recovery_teacher : TeacherModule | None, optional
        An optional DSPy module for generating recovery plans after an
        epistemic deadlock.  If ``None``, the primary *teacher* is used.
    dag_executor : Callable[[IntentionDAG, BeliefState], BeliefState] | None
        An optional callable that *executes* a verified DAG and returns the
        updated belief state.  When ``None``, the engine simply commits the
        belief state as-is (useful for simulation / PlanBench).
    """

    def __init__(
        self,
        verifier: BaseDomainVerifier,
        teacher: TeacherModule,
        *,
        max_retries: int = MAX_RETRIES,
        recovery_teacher: Optional[TeacherModule] = None,
        dag_executor: Optional[
            Callable[[IntentionDAG, BeliefState], BeliefState]
        ] = None,
    ) -> None:
        self.verifier: BaseDomainVerifier = verifier
        self.teacher: TeacherModule = teacher
        self.max_retries: int = max_retries
        self.recovery_teacher: TeacherModule = recovery_teacher or teacher
        self.dag_executor: Optional[
            Callable[[IntentionDAG, BeliefState], BeliefState]
        ] = dag_executor

        # The canonical belief state – mutated **only** after successful
        # verification.
        self.belief_state: BeliefState = BeliefState()

        # FIFO queue of desires / goals (each represented as a generic dict).
        self.desire_queue: deque[Dict[str, Any]] = deque()

        # Accumulated golden trajectories.
        self.golden_trajectories: List[GoldenTrajectory] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_desire(self, desire: Dict[str, Any]) -> None:
        """Enqueue a new desire / goal for the BDI engine to resolve.

        Parameters
        ----------
        desire : Dict[str, Any]
            A domain-agnostic description of the goal.
        """
        self.desire_queue.append(desire)
        logger.info("Desire enqueued: %s", desire)

    def run(self) -> List[GoldenTrajectory]:
        """Execute the full BDI deliberation cycle over all queued desires.

        For each desire in the queue the engine will:

        1. Prompt the Teacher LLM to produce an :class:`IntentionDAG`.
        2. Verify the DAG against a deep copy of the current belief state.
        3. On success – execute, commit belief-state updates, and log the
           golden trajectory.
        4. On failure – inject error context and retry (up to
           ``max_retries``).
        5. On epistemic deadlock – suspend the intention and attempt a
           recovery plan.

        Returns
        -------
        List[GoldenTrajectory]
            All golden trajectories produced during this run.
        """
        while self.desire_queue:
            desire = self.desire_queue.popleft()
            logger.info("Processing desire: %s", desire)
            self._process_desire(desire)

        return self.golden_trajectories

    # ------------------------------------------------------------------
    # JSON Extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_json_dag(raw_response: str) -> dict:
        """Extract a JSON dictionary from a potentially noisy LLM response.

        The method uses a two-stage strategy:

        1. **Regex extraction**: locate the first ``{`` and the last ``}``
           in *raw_response* and attempt to parse the substring as JSON.
        2. **Direct fallback**: if regex extraction fails, attempt
           ``json.loads`` on the entire *raw_response*.

        Parameters
        ----------
        raw_response : str
            The raw text output from the Teacher LLM, which may contain
            markdown fences, conversational filler, or other noise.

        Returns
        -------
        dict
            A parsed JSON dictionary.

        Raises
        ------
        ValueError
            If neither extraction strategy yields a valid JSON dict.
        """
        # ── Stage 1: regex-based extraction (first '{' to last '}') ──
        first_brace = raw_response.find("{")
        last_brace = raw_response.rfind("}")

        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            candidate = raw_response[first_brace : last_brace + 1]
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                logger.debug(
                    "Regex-extracted substring was not valid JSON; "
                    "falling through to direct parse."
                )

        # ── Stage 2: direct json.loads on the full response ──
        try:
            parsed = json.loads(raw_response.strip())
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        raise ValueError(
            "Failed to extract a valid JSON dict from the LLM response. "
            f"Response (first 200 chars): {raw_response[:200]!r}"
        )

    # ------------------------------------------------------------------
    # Internal Deliberation Logic
    # ------------------------------------------------------------------

    def _process_desire(self, desire: Dict[str, Any]) -> None:
        """Attempt to resolve a single desire through the BDI cycle.

        This method implements the core retry loop with epistemic deadlock
        detection.

        Parameters
        ----------
        desire : Dict[str, Any]
            The goal / desire to resolve.
        """
        retries: int = 0
        dag_dict: Dict[str, Any] = {}
        error_traces: List[str] = []
        correction_hints: List[str] = []
        error_correction_history: List[Dict[str, Any]] = []

        while retries <= self.max_retries:
            # ── 1. Snapshot the belief state before generation ──
            belief_snapshot = copy.deepcopy(self.belief_state)

            # ── 2. Prompt the Teacher LLM ──
            try:
                teacher_output = self._invoke_teacher(
                    desire=desire,
                    error_traces=error_traces,
                    correction_hints=correction_hints,
                )
            except Exception:
                logger.exception(
                    "Teacher LLM invocation failed for desire %s", desire
                )
                retries += 1
                error_traces.append("TeacherInvocationError: LLM call failed.")
                correction_hints.append(
                    "The previous LLM call failed. Retry with a simpler plan."
                )
                error_correction_history.append(
                    {
                        "attempt": retries,
                        "error_trace": error_traces[-1],
                        "correction_hint": correction_hints[-1],
                    }
                )
                continue

            # ── 3. Extract and parse the DAG JSON ──
            reasoning: str = getattr(teacher_output, "reasoning", "")
            raw_dag_json: str = getattr(
                teacher_output, "intention_dag_json", ""
            )

            try:
                dag_dict = self.extract_json_dag(raw_dag_json)
            except ValueError as exc:
                logger.warning("JSON extraction failed: %s", exc)
                retries += 1
                trace = f"JSONExtractionError: {exc}"
                hint = (
                    "Your previous response could not be parsed as JSON. "
                    "Return a valid JSON object with keys: dag_id, nodes, "
                    "metadata."
                )
                error_traces.append(trace)
                correction_hints.append(hint)
                error_correction_history.append(
                    {
                        "attempt": retries,
                        "error_trace": trace,
                        "correction_hint": hint,
                    }
                )
                continue

            # ── 4. Hydrate into Pydantic model ──
            try:
                intention_dag = self._hydrate_dag(dag_dict, desire)
            except Exception as exc:
                logger.warning("DAG hydration failed: %s", exc)
                retries += 1
                trace = f"DAGHydrationError: {exc}"
                hint = (
                    "Your JSON could not be parsed into a valid IntentionDAG. "
                    "Ensure the JSON has 'dag_id' (str), 'nodes' (list of "
                    "objects with 'node_id', 'action_type', 'parameters', "
                    "'dependencies'), and 'metadata' (object)."
                )
                error_traces.append(trace)
                correction_hints.append(hint)
                error_correction_history.append(
                    {
                        "attempt": retries,
                        "error_trace": trace,
                        "correction_hint": hint,
                    }
                )
                continue

            # ── 5. Verify against a DEEP COPY of the belief state ──
            belief_copy = copy.deepcopy(self.belief_state)
            is_valid, formal_error_trace, dspy_correction_hint = (
                self.verifier.verify_transition(belief_copy, intention_dag)
            )

            if is_valid:
                # ── 6a. Success path ──
                logger.info(
                    "Verification passed for DAG '%s'.", intention_dag.dag_id
                )
                # Execute the DAG (optionally via a custom executor).
                if self.dag_executor is not None:
                    self.belief_state = self.dag_executor(
                        intention_dag, copy.deepcopy(self.belief_state)
                    )
                # else: belief state stays as-is (simulation mode).

                # Log the golden trajectory.
                trajectory = GoldenTrajectory(
                    desire=desire,
                    intention_dag=intention_dag,
                    belief_before=belief_snapshot,
                    belief_after=copy.deepcopy(self.belief_state),
                    reasoning=reasoning,
                    error_correction_history=error_correction_history,
                )
                self.golden_trajectories.append(trajectory)
                logger.info(
                    "Golden trajectory recorded for desire: %s", desire
                )
                return  # Desire resolved ✓

            # ── 6b. Failure path – inject context and retry ──
            retries += 1
            error_traces.append(formal_error_trace)
            correction_hints.append(dspy_correction_hint)
            error_correction_history.append(
                {
                    "attempt": retries,
                    "error_trace": formal_error_trace,
                    "correction_hint": dspy_correction_hint,
                }
            )
            logger.warning(
                "Verification failed (attempt %d/%d) for DAG '%s': %s",
                retries,
                self.max_retries,
                intention_dag.dag_id,
                formal_error_trace,
            )

        # ── Epistemic Deadlock – retries exhausted ──
        self._handle_deadlock(
            desire=desire,
            dag_dict=dag_dict,  # type: ignore[possibly-undefined]
            error_traces=error_traces,
            correction_hints=correction_hints,
        )

    # ------------------------------------------------------------------
    # Teacher LLM Invocation
    # ------------------------------------------------------------------

    def _invoke_teacher(
        self,
        desire: Dict[str, Any],
        error_traces: List[str],
        correction_hints: List[str],
    ) -> Any:
        """Call the Teacher LLM with the current BDI context.

        Parameters
        ----------
        desire : Dict[str, Any]
            The goal / desire being pursued.
        error_traces : List[str]
            Accumulated formal error traces from previous failed attempts.
        correction_hints : List[str]
            Accumulated correction hints from previous failed attempts.

        Returns
        -------
        Any
            The teacher module's output (expected to have ``.reasoning`` and
            ``.intention_dag_json`` attributes).
        """
        kwargs: Dict[str, Any] = {
            "belief_state": self.belief_state.model_dump_json(),
            "desire": json.dumps(desire),
            "domain_context": json.dumps(
                self.belief_state.environment_context
            ),
        }

        # Inject prior failure context when retrying.
        if error_traces:
            kwargs["error_trace"] = error_traces[-1]
            kwargs["correction_hint"] = correction_hints[-1]
            kwargs["failed_attempts_summary"] = json.dumps(
                [
                    {"trace": t, "hint": h}
                    for t, h in zip(error_traces, correction_hints)
                ]
            )

        return self.teacher(**kwargs)

    # ------------------------------------------------------------------
    # DAG Hydration
    # ------------------------------------------------------------------

    @staticmethod
    def _hydrate_dag(
        dag_dict: Dict[str, Any],
        desire: Dict[str, Any],
    ) -> IntentionDAG:
        """Convert a raw JSON dict into a validated :class:`IntentionDAG`.

        Missing top-level keys are filled with sensible defaults so that the
        engine can handle slightly imperfect LLM output gracefully.

        Parameters
        ----------
        dag_dict : Dict[str, Any]
            The parsed JSON dictionary.
        desire : Dict[str, Any]
            The desire associated with this DAG (used for default metadata).

        Returns
        -------
        IntentionDAG
            A validated Pydantic model.
        """
        # Ensure a dag_id exists.
        if "dag_id" not in dag_dict:
            dag_dict["dag_id"] = f"dag-{uuid.uuid4().hex[:8]}"

        # Ensure metadata exists.
        if "metadata" not in dag_dict:
            dag_dict["metadata"] = {}
        dag_dict["metadata"].setdefault("source_desire", desire)

        return IntentionDAG.model_validate(dag_dict)

    # ------------------------------------------------------------------
    # Epistemic Deadlock Handling
    # ------------------------------------------------------------------

    def _handle_deadlock(
        self,
        desire: Dict[str, Any],
        dag_dict: Dict[str, Any],
        error_traces: List[str],
        correction_hints: List[str],
    ) -> None:
        """Handle an epistemic deadlock after retries are exhausted.

        1. Build the last known :class:`IntentionDAG` (best-effort).
        2. Raise :class:`EpistemicDeadlockError`.
        3. Catch it, suspend the failed intention in
           :attr:`BeliefState.suspended_intentions`.
        4. Compress traces into epistemic memory flags.
        5. Invoke the recovery teacher to generate a recovery plan.

        Parameters
        ----------
        desire : Dict[str, Any]
            The desire that could not be resolved.
        dag_dict : Dict[str, Any]
            The last parsed (but unverified) DAG dict.
        error_traces : List[str]
            All accumulated formal error traces.
        correction_hints : List[str]
            All accumulated correction hints.
        """
        # Best-effort construction of the failed DAG.
        try:
            failed_dag = self._hydrate_dag(dag_dict, desire)
        except Exception:
            failed_dag = IntentionDAG(
                dag_id=f"failed-{uuid.uuid4().hex[:8]}", metadata={"desire": desire}
            )

        # Compress traces for epistemic memory.
        compressed: List[str] = [
            t[:200] for t in error_traces  # Truncate long traces.
        ]

        try:
            raise EpistemicDeadlockError(
                failed_intention=failed_dag,
                retry_count=self.max_retries,
                compressed_traces=compressed,
            )
        except EpistemicDeadlockError as deadlock:
            logger.error("Epistemic deadlock: %s", deadlock)

            # ── Suspend the intention ──
            self.belief_state.suspended_intentions.append(
                deadlock.failed_intention
            )

            # ── Inject compressed traces into epistemic flags ──
            self.belief_state.epistemic_flags[
                f"deadlock_{failed_dag.dag_id}"
            ] = {
                "compressed_traces": deadlock.compressed_traces,
                "retry_count": deadlock.retry_count,
                "desire": desire,
            }

            # ── Force recovery plan generation ──
            self._attempt_recovery(desire)

    def _attempt_recovery(self, original_desire: Dict[str, Any]) -> None:
        """Invoke the recovery teacher to generate a recovery plan.

        The recovery teacher receives the suspended intentions and epistemic
        flags to produce a plan that unblocks the agent.

        Parameters
        ----------
        original_desire : Dict[str, Any]
            The desire that triggered the deadlock, provided for context.
        """
        try:
            recovery_output = self.recovery_teacher(
                suspended_intentions=json.dumps(
                    [
                        dag.model_dump()
                        for dag in self.belief_state.suspended_intentions
                    ]
                ),
                epistemic_flags=json.dumps(
                    self.belief_state.epistemic_flags
                ),
            )
            logger.info(
                "Recovery plan generated for desire %s: %s",
                original_desire,
                getattr(recovery_output, "recovery_plan_json", "N/A"),
            )
        except Exception:
            logger.exception(
                "Recovery teacher failed for desire %s. "
                "Intention remains suspended.",
                original_desire,
            )
