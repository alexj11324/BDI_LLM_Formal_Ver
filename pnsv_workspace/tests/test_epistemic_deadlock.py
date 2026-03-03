"""Unit tests for Epistemic Deadlock triggering and task suspension.

Covers:
- EpistemicDeadlockError construction and attributes
- BDI engine deadlock detection after max retries exceeded
- Task suspension into BeliefState.suspended_intentions
- Compressed traces injection into epistemic_flags
- Recovery teacher invocation after deadlock
- Deadlock with custom max_retries
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.core.bdi_engine import BDIEngine, GoldenTrajectory, MAX_RETRIES
from src.core.exceptions import EpistemicDeadlockError
from src.core.schemas import BeliefState, IntentionDAG, IntentionNode
from src.core.verification_bus import BaseDomainVerifier


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


class AlwaysFailVerifier(BaseDomainVerifier):
    """A verifier that always rejects the DAG.

    Used to force the BDI engine into epistemic deadlock.
    """

    def __init__(self, error_trace: str = "SimulatedFailure: test", hint: str = "Fix the plan.") -> None:
        self._error_trace = error_trace
        self._hint = hint
        self.call_count: int = 0

    def verify_transition(
        self,
        current_belief: BeliefState,
        intention_dag: IntentionDAG,
    ) -> tuple[bool, str, str]:
        """Always returns failure."""
        self.call_count += 1
        return (False, self._error_trace, self._hint)


class AlwaysPassVerifier(BaseDomainVerifier):
    """A verifier that always accepts the DAG."""

    def verify_transition(
        self,
        current_belief: BeliefState,
        intention_dag: IntentionDAG,
    ) -> tuple[bool, str, str]:
        """Always returns success."""
        return (True, "", "")


class FailThenPassVerifier(BaseDomainVerifier):
    """Fails *n* times, then passes on subsequent calls."""

    def __init__(self, failures_before_pass: int = 2) -> None:
        self._failures_before_pass = failures_before_pass
        self.call_count: int = 0

    def verify_transition(
        self,
        current_belief: BeliefState,
        intention_dag: IntentionDAG,
    ) -> tuple[bool, str, str]:
        """Fail for the first N calls, then pass."""
        self.call_count += 1
        if self.call_count <= self._failures_before_pass:
            return (
                False,
                f"Failure #{self.call_count}: precondition violated",
                f"Hint: fix attempt #{self.call_count}",
            )
        return (True, "", "")


def _make_teacher(dag_json: str | None = None) -> MagicMock:
    """Create a mock DSPy teacher that returns a fixed DAG JSON."""
    if dag_json is None:
        dag_json = json.dumps({
            "dag_id": "test-dag",
            "nodes": [
                {
                    "node_id": "n1",
                    "action_type": "test-action",
                    "parameters": {"key": "value"},
                    "dependencies": [],
                }
            ],
            "metadata": {},
        })

    mock = MagicMock()
    output = MagicMock()
    output.reasoning = "Test reasoning chain"
    output.intention_dag_json = dag_json
    mock.return_value = output
    return mock


# ---------------------------------------------------------------------------
# EpistemicDeadlockError Construction
# ---------------------------------------------------------------------------


class TestEpistemicDeadlockError:
    """Tests for the custom exception itself."""

    def test_basic_construction(self) -> None:
        """Exception should store all attributes."""
        dag = IntentionDAG(dag_id="fail-dag")
        error = EpistemicDeadlockError(
            failed_intention=dag,
            retry_count=3,
            compressed_traces=["trace1", "trace2"],
        )
        assert error.failed_intention is dag
        assert error.retry_count == 3
        assert error.compressed_traces == ["trace1", "trace2"]

    def test_auto_generated_message(self) -> None:
        """Default message should include dag_id and retry_count."""
        dag = IntentionDAG(dag_id="my-dag")
        error = EpistemicDeadlockError(
            failed_intention=dag,
            retry_count=5,
            compressed_traces=["t1"],
        )
        assert "my-dag" in str(error)
        assert "5" in str(error)

    def test_custom_message(self) -> None:
        """Custom message should override the default."""
        dag = IntentionDAG(dag_id="d1")
        error = EpistemicDeadlockError(
            failed_intention=dag,
            retry_count=1,
            compressed_traces=[],
            message="custom error",
        )
        assert str(error) == "custom error"

    def test_is_exception(self) -> None:
        """Should be catchable as a base Exception."""
        dag = IntentionDAG(dag_id="d1")
        with pytest.raises(Exception):
            raise EpistemicDeadlockError(
                failed_intention=dag,
                retry_count=1,
                compressed_traces=[],
            )


# ---------------------------------------------------------------------------
# BDI Engine Deadlock Triggering
# ---------------------------------------------------------------------------


class TestDeadlockTriggering:
    """Tests that verify the BDI engine correctly triggers epistemic deadlock."""

    def test_deadlock_after_max_retries(self) -> None:
        """Engine should trigger deadlock and suspend intention after exhausting retries."""
        verifier = AlwaysFailVerifier()
        teacher = _make_teacher()
        recovery_teacher = _make_teacher()

        engine = BDIEngine(
            verifier=verifier,
            teacher=teacher,
            max_retries=3,
            recovery_teacher=recovery_teacher,
        )

        engine.add_desire({"goal": "test-goal"})
        engine.run()

        # The intention should be suspended.
        assert len(engine.belief_state.suspended_intentions) == 1
        suspended_dag = engine.belief_state.suspended_intentions[0]
        assert isinstance(suspended_dag, IntentionDAG)

        # The verifier should have been called max_retries + 1 times
        # (initial attempt + max_retries retries).
        assert verifier.call_count == 4  # 0, 1, 2, 3 retries

        # No golden trajectories should have been produced.
        assert len(engine.golden_trajectories) == 0

    def test_deadlock_injects_epistemic_flags(self) -> None:
        """After deadlock, compressed traces should be injected into epistemic_flags."""
        verifier = AlwaysFailVerifier(
            error_trace="PreconditionViolation: test failed",
            hint="Check preconditions",
        )
        teacher = _make_teacher()

        engine = BDIEngine(
            verifier=verifier,
            teacher=teacher,
            max_retries=2,
        )

        engine.add_desire({"goal": "deadlock-test"})
        engine.run()

        # Check that epistemic flags were set.
        assert len(engine.belief_state.epistemic_flags) > 0
        # Find the deadlock flag.
        deadlock_keys = [
            k for k in engine.belief_state.epistemic_flags
            if k.startswith("deadlock_")
        ]
        assert len(deadlock_keys) == 1

        flag_data = engine.belief_state.epistemic_flags[deadlock_keys[0]]
        assert "compressed_traces" in flag_data
        assert "retry_count" in flag_data
        assert "desire" in flag_data
        assert flag_data["retry_count"] == 2

    def test_recovery_teacher_invoked_after_deadlock(self) -> None:
        """The recovery teacher should be called when deadlock occurs."""
        verifier = AlwaysFailVerifier()
        teacher = _make_teacher()
        recovery_teacher = _make_teacher()

        engine = BDIEngine(
            verifier=verifier,
            teacher=teacher,
            max_retries=1,
            recovery_teacher=recovery_teacher,
        )

        engine.add_desire({"goal": "recovery-test"})
        engine.run()

        # Recovery teacher should have been called.
        recovery_teacher.assert_called_once()

        # Check that the recovery teacher received the right kwargs.
        call_kwargs = recovery_teacher.call_args[1]
        assert "suspended_intentions" in call_kwargs
        assert "epistemic_flags" in call_kwargs

    def test_custom_max_retries(self) -> None:
        """Engine should respect a custom max_retries value."""
        verifier = AlwaysFailVerifier()
        teacher = _make_teacher()

        engine = BDIEngine(
            verifier=verifier,
            teacher=teacher,
            max_retries=1,
        )

        engine.add_desire({"goal": "quick-fail"})
        engine.run()

        # Only 2 calls: initial attempt + 1 retry.
        assert verifier.call_count == 2
        assert len(engine.belief_state.suspended_intentions) == 1


# ---------------------------------------------------------------------------
# Task Suspension Mechanics
# ---------------------------------------------------------------------------


class TestTaskSuspension:
    """Tests for the task suspension mechanism."""

    def test_suspended_dag_preserved(self) -> None:
        """The suspended DAG should remain accessible in belief state."""
        verifier = AlwaysFailVerifier()
        teacher = _make_teacher()

        engine = BDIEngine(verifier=verifier, teacher=teacher, max_retries=0)
        engine.add_desire({"goal": "suspend-me"})
        engine.run()

        suspended = engine.belief_state.suspended_intentions
        assert len(suspended) == 1
        assert isinstance(suspended[0], IntentionDAG)
        assert suspended[0].dag_id  # Should have a valid dag_id.

    def test_multiple_deadlocks_accumulate_suspensions(self) -> None:
        """Multiple deadlocked desires should each produce a suspension."""
        # Use a teacher function that produces distinct dag_ids per call
        # so that epistemic_flag keys don't collide.
        verifier = AlwaysFailVerifier()
        call_counter = {"n": 0}

        def teacher_fn(**kwargs: Any) -> MagicMock:
            call_counter["n"] += 1
            output = MagicMock()
            output.reasoning = f"reasoning-{call_counter['n']}"
            output.intention_dag_json = json.dumps({
                "dag_id": f"dag-task-{call_counter['n']}",
                "nodes": [{"node_id": "n1", "action_type": "a", "parameters": {}, "dependencies": []}],
                "metadata": {},
            })
            # Also handle recovery calls (which use different kwargs).
            output.recovery_plan_json = "{}"
            return output

        teacher = MagicMock(side_effect=teacher_fn)
        recovery_teacher = MagicMock(side_effect=teacher_fn)

        engine = BDIEngine(
            verifier=verifier,
            teacher=teacher,
            max_retries=0,
            recovery_teacher=recovery_teacher,
        )
        engine.add_desire({"goal": "task-1"})
        engine.add_desire({"goal": "task-2"})
        engine.run()

        assert len(engine.belief_state.suspended_intentions) == 2
        assert len(engine.belief_state.epistemic_flags) == 2

    def test_no_suspension_on_success(self) -> None:
        """Successful verification should NOT produce any suspensions."""
        verifier = AlwaysPassVerifier()
        teacher = _make_teacher()

        engine = BDIEngine(verifier=verifier, teacher=teacher)
        engine.add_desire({"goal": "success-test"})
        engine.run()

        assert len(engine.belief_state.suspended_intentions) == 0
        assert len(engine.golden_trajectories) == 1


# ---------------------------------------------------------------------------
# Retry + Success (no deadlock)
# ---------------------------------------------------------------------------


class TestRetryWithoutDeadlock:
    """Verify that the engine retries and can succeed before deadlock."""

    def test_fails_then_succeeds(self) -> None:
        """Engine should retry and eventually succeed without deadlocking."""
        verifier = FailThenPassVerifier(failures_before_pass=2)
        teacher = _make_teacher()

        engine = BDIEngine(verifier=verifier, teacher=teacher, max_retries=3)
        engine.add_desire({"goal": "retry-success"})
        engine.run()

        # Should have succeeded on the 3rd call (after 2 failures).
        assert verifier.call_count == 3
        assert len(engine.golden_trajectories) == 1
        assert len(engine.belief_state.suspended_intentions) == 0

        # The golden trajectory should record the error correction history.
        trajectory = engine.golden_trajectories[0]
        assert len(trajectory.error_correction_history) == 2  # 2 failed attempts

    def test_recovery_not_invoked_on_success(self) -> None:
        """Recovery teacher should NOT be called when verification eventually passes."""
        verifier = FailThenPassVerifier(failures_before_pass=1)
        teacher = _make_teacher()
        recovery_teacher = _make_teacher()

        engine = BDIEngine(
            verifier=verifier,
            teacher=teacher,
            max_retries=3,
            recovery_teacher=recovery_teacher,
        )

        engine.add_desire({"goal": "no-recovery-needed"})
        engine.run()

        recovery_teacher.assert_not_called()


# ---------------------------------------------------------------------------
# All-Retries-Fail Before DAG Parse (Bug Fix Regression)
# ---------------------------------------------------------------------------


class TestAllRetriesFailBeforeParse:
    """Regression test: engine must not crash when dag_dict was never assigned."""

    def test_deadlock_when_all_retries_fail_json_parse(self) -> None:
        """If every attempt fails at JSON extraction, _handle_deadlock should
        still work without raising UnboundLocalError."""
        verifier = AlwaysPassVerifier()
        teacher = MagicMock()

        bad_output = MagicMock()
        bad_output.reasoning = "thinking..."
        bad_output.intention_dag_json = "NOT VALID JSON {{{{"
        teacher.return_value = bad_output

        recovery_teacher = MagicMock()
        recovery_output = MagicMock()
        recovery_output.recovery_plan_json = "{}"
        recovery_teacher.return_value = recovery_output

        engine = BDIEngine(
            verifier=verifier,
            teacher=teacher,
            max_retries=2,
            recovery_teacher=recovery_teacher,
        )

        engine.add_desire({"goal": "json-parse-fail"})
        engine.run()

        assert len(engine.belief_state.suspended_intentions) == 1
        assert len(engine.golden_trajectories) == 0
        recovery_teacher.assert_called_once()
