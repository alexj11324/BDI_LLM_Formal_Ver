"""Unit tests for core Pydantic V2 schemas.

Covers:
- Valid construction of IntentionNode, IntentionDAG, BeliefState
- Invalid / missing field rejection
- Serialization round-trips (model_dump / model_dump_json / model_validate)
- Default factory isolation (no shared mutable defaults)
"""

from __future__ import annotations

import json
from typing import Any, Dict

import pytest
from pydantic import ValidationError

from src.core.schemas import BeliefState, IntentionDAG, IntentionNode


# ---------------------------------------------------------------------------
# IntentionNode
# ---------------------------------------------------------------------------

class TestIntentionNode:
    """Tests for the IntentionNode schema."""

    def test_valid_minimal(self) -> None:
        """Node with only required fields (node_id, action_type)."""
        node = IntentionNode(node_id="n1", action_type="pick-up")
        assert node.node_id == "n1"
        assert node.action_type == "pick-up"
        assert node.parameters == {}
        assert node.dependencies == []

    def test_valid_full(self) -> None:
        """Node with all fields specified."""
        node = IntentionNode(
            node_id="n2",
            action_type="unstack",
            parameters={"block": "A", "from_block": "B"},
            dependencies=["n1"],
        )
        assert node.parameters["block"] == "A"
        assert node.dependencies == ["n1"]

    def test_missing_node_id_raises(self) -> None:
        """Omitting node_id should raise ValidationError."""
        with pytest.raises(ValidationError):
            IntentionNode(action_type="pick-up")  # type: ignore[call-arg]

    def test_missing_action_type_raises(self) -> None:
        """Omitting action_type should raise ValidationError."""
        with pytest.raises(ValidationError):
            IntentionNode(node_id="n1")  # type: ignore[call-arg]

    def test_serialization_round_trip(self) -> None:
        """model_dump -> model_validate round-trip preserves data."""
        original = IntentionNode(
            node_id="n3",
            action_type="stack",
            parameters={"block": "C", "target": "D"},
            dependencies=["n1", "n2"],
        )
        dumped: Dict[str, Any] = original.model_dump()
        restored = IntentionNode.model_validate(dumped)
        assert restored == original

    def test_json_round_trip(self) -> None:
        """model_dump_json -> model_validate_json round-trip."""
        original = IntentionNode(node_id="n4", action_type="put-down")
        json_str = original.model_dump_json()
        restored = IntentionNode.model_validate_json(json_str)
        assert restored == original

    def test_default_factories_are_independent(self) -> None:
        """Each instance should get its own mutable default containers."""
        a = IntentionNode(node_id="a", action_type="x")
        b = IntentionNode(node_id="b", action_type="y")
        a.parameters["key"] = "val"
        assert "key" not in b.parameters


# ---------------------------------------------------------------------------
# IntentionDAG
# ---------------------------------------------------------------------------

class TestIntentionDAG:
    """Tests for the IntentionDAG schema."""

    def test_valid_empty_dag(self) -> None:
        """DAG with no nodes (valid structure)."""
        dag = IntentionDAG(dag_id="dag-empty")
        assert dag.dag_id == "dag-empty"
        assert dag.nodes == []
        assert dag.metadata == {}

    def test_valid_dag_with_nodes(self) -> None:
        """DAG with multiple nodes."""
        nodes = [
            IntentionNode(node_id="n1", action_type="pick-up", parameters={"block": "A"}),
            IntentionNode(node_id="n2", action_type="stack", parameters={"block": "A", "target": "B"}, dependencies=["n1"]),
        ]
        dag = IntentionDAG(dag_id="dag-1", nodes=nodes, metadata={"source": "test"})
        assert len(dag.nodes) == 2
        assert dag.metadata["source"] == "test"

    def test_missing_dag_id_raises(self) -> None:
        """Omitting dag_id should raise ValidationError."""
        with pytest.raises(ValidationError):
            IntentionDAG()  # type: ignore[call-arg]

    def test_invalid_node_type_raises(self) -> None:
        """Passing a non-node object in nodes should raise ValidationError."""
        with pytest.raises(ValidationError):
            IntentionDAG(dag_id="dag-bad", nodes=[{"not": "a node"}])  # type: ignore[arg-type]

    def test_serialization_round_trip(self) -> None:
        """model_dump -> model_validate round-trip."""
        dag = IntentionDAG(
            dag_id="dag-rt",
            nodes=[IntentionNode(node_id="n1", action_type="test")],
            metadata={"key": "value"},
        )
        dumped = dag.model_dump()
        restored = IntentionDAG.model_validate(dumped)
        assert restored == dag


# ---------------------------------------------------------------------------
# BeliefState
# ---------------------------------------------------------------------------

class TestBeliefState:
    """Tests for the BeliefState schema."""

    def test_default_construction(self) -> None:
        """All fields have defaults."""
        bs = BeliefState()
        assert bs.environment_context == {}
        assert bs.epistemic_flags == {}
        assert bs.suspended_intentions == []

    def test_full_construction(self) -> None:
        """Construct with all fields specified."""
        dag = IntentionDAG(dag_id="suspended-1")
        bs = BeliefState(
            environment_context={"pddl_state": ["clear(A)"]},
            epistemic_flags={"deadlock": True},
            suspended_intentions=[dag],
        )
        assert len(bs.suspended_intentions) == 1
        assert bs.environment_context["pddl_state"] == ["clear(A)"]

    def test_default_factories_isolation(self) -> None:
        """Each BeliefState gets independent default dicts/lists."""
        a = BeliefState()
        b = BeliefState()
        a.environment_context["key"] = "val"
        assert "key" not in b.environment_context

    def test_serialization_round_trip(self) -> None:
        """model_dump -> model_validate for BeliefState."""
        original = BeliefState(
            environment_context={"state": [1, 2, 3]},
            epistemic_flags={"flag": "set"},
        )
        restored = BeliefState.model_validate(original.model_dump())
        assert restored == original
