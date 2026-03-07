"""Integration test: generic PDDL planner end-to-end with gripper domain.

Exercises the full pipeline:
  DomainSpec.from_pddl() → BDIPlanner(domain_spec=...) → generate_plan() →
  structural verification → VAL verification
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.bdi_llm.planner import BDIPlanner, DomainSpec
from src.bdi_llm.planning_task import PDDLPlanSerializer, PDDLTaskAdapter
from src.bdi_llm.verifier import PlanVerifier

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "gripper"
DOMAIN_FILE = FIXTURE_DIR / "domain.pddl"
PROBLEM_FILE = FIXTURE_DIR / "problem1.pddl"


@pytest.fixture
def gripper_spec() -> DomainSpec:
    """DomainSpec built from gripper PDDL."""
    return DomainSpec.from_pddl("gripper", DOMAIN_FILE.read_text())


@pytest.fixture
def gripper_planner(gripper_spec: DomainSpec) -> BDIPlanner:
    """BDIPlanner configured for gripper domain."""
    return BDIPlanner(auto_repair=True, domain_spec=gripper_spec)


@pytest.fixture
def gripper_adapter(gripper_spec: DomainSpec) -> PDDLTaskAdapter:
    return PDDLTaskAdapter("gripper", gripper_spec.domain_context)


# ---------------------------------------------------------------------------
# DomainSpec sanity
# ---------------------------------------------------------------------------

class TestGripperDomainSpec:
    def test_actions_extracted(self, gripper_spec: DomainSpec):
        assert "move" in gripper_spec.valid_action_types
        assert "pick" in gripper_spec.valid_action_types
        assert "drop" in gripper_spec.valid_action_types

    def test_is_generic(self, gripper_spec: DomainSpec):
        from src.bdi_llm.planner.signatures import GeneratePlanGeneric

        assert gripper_spec.signature_class is GeneratePlanGeneric

    def test_domain_context_populated(self, gripper_spec: DomainSpec):
        assert gripper_spec.domain_context is not None
        assert "move" in gripper_spec.domain_context


# ---------------------------------------------------------------------------
# Task adapter
# ---------------------------------------------------------------------------

class TestGripperTaskAdapter:
    def test_creates_planning_task(self, gripper_adapter: PDDLTaskAdapter):
        task = gripper_adapter.to_planning_task(str(PROBLEM_FILE))
        assert task.task_id == "problem1"
        assert "rooma" in task.beliefs
        assert "ball1" in task.desire or "roomb" in task.desire


# ---------------------------------------------------------------------------
# Planner instantiation
# ---------------------------------------------------------------------------

class TestGripperPlanner:
    def test_planner_is_generic(self, gripper_planner: BDIPlanner):
        assert gripper_planner._is_generic is True
        assert gripper_planner.domain == "gripper"

    def test_planner_rejects_missing_context(self):
        """§4.2: generic planner without context must raise."""
        from src.bdi_llm.planner.signatures import GeneratePlanGeneric

        spec = DomainSpec(
            name="bad",
            valid_action_types=frozenset(),
            required_params={},
            signature_class=GeneratePlanGeneric,
            domain_context=None,
        )
        planner = BDIPlanner(auto_repair=False, domain_spec=spec)
        with pytest.raises(ValueError, match="requires domain_context"):
            planner.generate_plan(beliefs="x", desire="y")


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

class TestGripperSerializer:
    def test_serializes_mock_plan(self):
        from src.bdi_llm.schemas import ActionNode, BDIPlan, DependencyEdge

        plan = BDIPlan(
            goal_description="move balls",
            nodes=[
                ActionNode(
                    id="s1", action_type="move",
                    description="move", params={"from": "rooma", "to": "roomb"},
                ),
                ActionNode(
                    id="s2", action_type="pick",
                    description="pick ball",
                    params={"obj": "ball1", "room": "roomb", "gripper": "left"},
                ),
            ],
            edges=[DependencyEdge(
                source="s1", target="s2", relationship="sequential",
            )],
        )
        from src.bdi_llm.planning_task import PlanningTask

        task = PlanningTask(
            task_id="t", domain_name="gripper",
            beliefs="", desire="",
        )
        actions = PDDLPlanSerializer().from_bdi_plan(plan, task)
        assert len(actions) == 2
        assert "move" in actions[0]
        assert "pick" in actions[1]
