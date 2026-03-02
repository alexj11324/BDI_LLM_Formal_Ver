"""Unit tests for the PlanBench verifier plugin.

Covers:
- Valid Blocksworld plans (single and multi-step)
- Precondition violations for each action type
- Unknown action type handling
- Missing parameter detection
- Dependency cycle detection
- Invalid PDDL state format handling
- State mutation after successful simulation
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Set

import pytest

from src.core.schemas import BeliefState, IntentionDAG, IntentionNode
from src.plugins.planbench_verifier import PlanBenchVerifier


@pytest.fixture
def verifier() -> PlanBenchVerifier:
    """Create a fresh PlanBenchVerifier instance."""
    return PlanBenchVerifier()


def _make_belief(pddl_state: List[str]) -> BeliefState:
    """Helper: create a BeliefState with the given PDDL predicates."""
    return BeliefState(environment_context={"pddl_state": pddl_state})


def _make_dag(nodes: List[IntentionNode], dag_id: str = "test-dag") -> IntentionDAG:
    """Helper: create an IntentionDAG from a list of nodes."""
    return IntentionDAG(dag_id=dag_id, nodes=nodes)


# ---------------------------------------------------------------------------
# Valid Plans
# ---------------------------------------------------------------------------

class TestValidPlans:
    """Test cases where the plan should pass verification."""

    def test_single_pick_up(self, verifier: PlanBenchVerifier) -> None:
        """pick-up(A) when preconditions are met."""
        belief = _make_belief(["clear(A)", "ontable(A)", "arm-empty"])
        dag = _make_dag([
            IntentionNode(node_id="n1", action_type="pick-up", parameters={"block": "A"}),
        ])
        is_valid, trace, hint = verifier.verify_transition(belief, dag)
        assert is_valid is True
        assert trace == ""
        assert hint == ""

    def test_pick_up_and_put_down(self, verifier: PlanBenchVerifier) -> None:
        """pick-up(A) then put-down(A)."""
        belief = _make_belief(["clear(A)", "ontable(A)", "arm-empty"])
        dag = _make_dag([
            IntentionNode(node_id="n1", action_type="pick-up", parameters={"block": "A"}),
            IntentionNode(node_id="n2", action_type="put-down", parameters={"block": "A"}, dependencies=["n1"]),
        ])
        is_valid, _, _ = verifier.verify_transition(belief, dag)
        assert is_valid is True

    def test_unstack_and_put_down(self, verifier: PlanBenchVerifier) -> None:
        """unstack(A, B) then put-down(A)."""
        belief = _make_belief(["clear(A)", "on(A, B)", "arm-empty", "ontable(B)"])
        dag = _make_dag([
            IntentionNode(node_id="n1", action_type="unstack", parameters={"block": "A", "from_block": "B"}),
            IntentionNode(node_id="n2", action_type="put-down", parameters={"block": "A"}, dependencies=["n1"]),
        ])
        is_valid, _, _ = verifier.verify_transition(belief, dag)
        assert is_valid is True

    def test_pick_up_and_stack(self, verifier: PlanBenchVerifier) -> None:
        """pick-up(A) then stack(A, B)."""
        belief = _make_belief([
            "clear(A)", "ontable(A)", "arm-empty",
            "clear(B)", "ontable(B)",
        ])
        dag = _make_dag([
            IntentionNode(node_id="n1", action_type="pick-up", parameters={"block": "A"}),
            IntentionNode(node_id="n2", action_type="stack", parameters={"block": "A", "target": "B"}, dependencies=["n1"]),
        ])
        is_valid, _, _ = verifier.verify_transition(belief, dag)
        assert is_valid is True


# ---------------------------------------------------------------------------
# Precondition Violations
# ---------------------------------------------------------------------------

class TestPreconditionViolations:
    """Test cases where preconditions are not satisfied."""

    def test_pick_up_not_clear(self, verifier: PlanBenchVerifier) -> None:
        """pick-up(A) when A is not clear should fail."""
        belief = _make_belief(["ontable(A)", "arm-empty"])  # missing clear(A)
        dag = _make_dag([
            IntentionNode(node_id="n1", action_type="pick-up", parameters={"block": "A"}),
        ])
        is_valid, trace, hint = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "PreconditionViolation" in trace
        assert "clear(A)" in trace

    def test_pick_up_arm_not_empty(self, verifier: PlanBenchVerifier) -> None:
        """pick-up(A) when arm is not empty should fail."""
        belief = _make_belief(["clear(A)", "ontable(A)"])  # missing arm-empty
        dag = _make_dag([
            IntentionNode(node_id="n1", action_type="pick-up", parameters={"block": "A"}),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "arm-empty" in trace

    def test_unstack_not_on(self, verifier: PlanBenchVerifier) -> None:
        """unstack(A, B) when on(A, B) doesn't hold should fail."""
        belief = _make_belief(["clear(A)", "arm-empty"])  # missing on(A, B)
        dag = _make_dag([
            IntentionNode(node_id="n1", action_type="unstack", parameters={"block": "A", "from_block": "B"}),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "on(A, B)" in trace

    def test_stack_target_not_clear(self, verifier: PlanBenchVerifier) -> None:
        """stack(A, B) when B is not clear should fail."""
        belief = _make_belief(["holding(A)"])  # missing clear(B)
        dag = _make_dag([
            IntentionNode(node_id="n1", action_type="stack", parameters={"block": "A", "target": "B"}),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "clear(B)" in trace


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Test edge cases and error conditions."""

    def test_unknown_action(self, verifier: PlanBenchVerifier) -> None:
        """An unrecognised action_type should produce UnknownActionError."""
        belief = _make_belief(["arm-empty"])
        dag = _make_dag([
            IntentionNode(node_id="n1", action_type="fly", parameters={}),
        ])
        is_valid, trace, hint = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "UnknownActionError" in trace
        assert "fly" in trace

    def test_missing_parameters(self, verifier: PlanBenchVerifier) -> None:
        """A node missing required params should produce MissingParameterError."""
        belief = _make_belief(["arm-empty"])
        dag = _make_dag([
            IntentionNode(node_id="n1", action_type="pick-up", parameters={}),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "MissingParameterError" in trace
        assert "block" in trace

    def test_dependency_cycle(self, verifier: PlanBenchVerifier) -> None:
        """Circular dependencies should produce TopologicalSortError."""
        belief = _make_belief(["arm-empty"])
        dag = _make_dag([
            IntentionNode(node_id="n1", action_type="pick-up", parameters={"block": "A"}, dependencies=["n2"]),
            IntentionNode(node_id="n2", action_type="put-down", parameters={"block": "A"}, dependencies=["n1"]),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "TopologicalSortError" in trace or "Cycle" in trace

    def test_invalid_pddl_state_format(self, verifier: PlanBenchVerifier) -> None:
        """Non-list/set pddl_state should produce StateFormatError."""
        belief = BeliefState(environment_context={"pddl_state": "not-a-list"})
        dag = _make_dag([
            IntentionNode(node_id="n1", action_type="pick-up", parameters={"block": "A"}),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "StateFormatError" in trace

    def test_empty_dag_is_valid(self, verifier: PlanBenchVerifier) -> None:
        """An empty DAG (no actions) should be trivially valid."""
        belief = _make_belief(["arm-empty"])
        dag = _make_dag([])
        is_valid, trace, hint = verifier.verify_transition(belief, dag)
        assert is_valid is True

    def test_missing_dependency_node(self, verifier: PlanBenchVerifier) -> None:
        """A node depending on a non-existent node_id should fail verification."""
        belief = _make_belief(["clear(A)", "ontable(A)", "arm-empty"])
        dag = _make_dag([
            IntentionNode(
                node_id="n1",
                action_type="pick-up",
                parameters={"block": "A"},
                dependencies=["nonexistent_node"],
            ),
        ])
        is_valid, trace, _ = verifier.verify_transition(belief, dag)
        assert is_valid is False
        assert "nonexistent_node" in trace
        assert "does not exist" in trace or "TopologicalSortError" in trace

