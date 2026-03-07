"""Unit tests for PlanningTask abstractions and PDDL implementations."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.bdi_llm.planning_task import (
    PDDLPlanSerializer,
    PDDLTaskAdapter,
    PlanningTask,
    _parse_pddl_goal,
    _parse_pddl_init,
    _parse_pddl_objects,
)
from src.bdi_llm.schemas import ActionNode, BDIPlan, DependencyEdge

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GRIPPER_PROBLEM = textwrap.dedent("""\
    (define (problem gripper-1)
      (:domain gripper)
      (:objects rooma roomb left right ball1 ball2)
      (:init
        (room rooma) (room roomb)
        (gripper left) (gripper right)
        (ball ball1) (ball ball2)
        (at-robby rooma)
        (at ball1 rooma) (at ball2 rooma)
        (free left) (free right))
      (:goal (and (at ball1 roomb) (at ball2 roomb))))
""")

TYPED_PROBLEM = textwrap.dedent("""\
    (define (problem typed-1)
      (:domain typed-test)
      (:objects
        truck1 truck2 - vehicle
        cityA cityB - location)
      (:init
        (at truck1 cityA)
        (at truck2 cityB))
      (:goal (at truck1 cityB)))
""")

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "gripper"


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

class TestParseObjects:
    def test_untyped_objects(self):
        result = _parse_pddl_objects(GRIPPER_PROBLEM)
        assert "Objects:" in result
        assert "rooma" in result
        assert "ball1" in result

    def test_typed_objects(self):
        result = _parse_pddl_objects(TYPED_PROBLEM)
        assert "(type: vehicle)" in result
        assert "truck1" in result
        assert "(type: location)" in result
        assert "cityA" in result

    def test_no_objects_block(self):
        assert _parse_pddl_objects("(define (problem x))") == ""


class TestParseInit:
    def test_extracts_predicates(self):
        result = _parse_pddl_init(GRIPPER_PROBLEM)
        assert "Initial state:" in result
        assert "(room rooma)" in result
        assert "(at-robby rooma)" in result
        assert "(free left)" in result

    def test_no_init(self):
        result = _parse_pddl_init("no init here")
        assert result == "no init here"


class TestParseGoal:
    def test_and_wrapped_goals(self):
        result = _parse_pddl_goal(GRIPPER_PROBLEM)
        assert "Goal conditions:" in result
        assert "(at ball1 roomb)" in result
        assert "(at ball2 roomb)" in result

    def test_single_goal(self):
        result = _parse_pddl_goal(TYPED_PROBLEM)
        assert "at truck1 cityB" in result

    def test_no_goal(self):
        result = _parse_pddl_goal("(define (problem x))")
        assert result == ""


# ---------------------------------------------------------------------------
# PDDLTaskAdapter
# ---------------------------------------------------------------------------

class TestPDDLTaskAdapter:
    def test_from_file_path(self):
        problem_file = FIXTURE_DIR / "problem1.pddl"
        if not problem_file.exists():
            pytest.skip(f"Fixture not found: {problem_file}")

        adapter = PDDLTaskAdapter("gripper", domain_context="test context")
        task = adapter.to_planning_task(str(problem_file))

        assert isinstance(task, PlanningTask)
        assert task.task_id == "problem1"
        assert task.domain_name == "gripper"
        assert task.domain_context == "test context"
        assert "rooma" in task.beliefs
        assert "ball1" in task.beliefs
        assert "ball1" in task.desire or "roomb" in task.desire

    def test_from_dict(self):
        adapter = PDDLTaskAdapter("gripper")
        task = adapter.to_planning_task({
            "problem_text": GRIPPER_PROBLEM,
            "task_id": "test-1",
        })
        assert task.task_id == "test-1"
        assert "rooma" in task.beliefs

    def test_missing_file_raises(self):
        adapter = PDDLTaskAdapter("gripper")
        with pytest.raises(FileNotFoundError):
            adapter.to_planning_task("/nonexistent/problem.pddl")

    def test_bad_input_type_raises(self):
        adapter = PDDLTaskAdapter("gripper")
        with pytest.raises(TypeError):
            adapter.to_planning_task(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# PDDLPlanSerializer
# ---------------------------------------------------------------------------

def _make_simple_plan() -> BDIPlan:
    """Create a simple 2-node plan with dependencies."""
    n1 = ActionNode(
        id="step1", action_type="move",
        description="Move to room B",
        params={"from": "rooma", "to": "roomb"},
    )
    n2 = ActionNode(
        id="step2", action_type="pick",
        description="Pick ball",
        params={"obj": "ball1", "room": "roomb", "gripper": "left"},
    )
    edge = DependencyEdge(source="step1", target="step2", relationship="sequential")
    return BDIPlan(
        goal_description="pick ball in room B",
        nodes=[n1, n2],
        edges=[edge],
    )


def _make_no_edge_plan() -> BDIPlan:
    """Plan with no edges — should fall back to node insertion order."""
    n1 = ActionNode(
        id="a", action_type="move",
        description="move",
        params={"from": "x", "to": "y"},
    )
    n2 = ActionNode(
        id="b", action_type="pick",
        description="pick",
        params={"obj": "ball"},
    )
    return BDIPlan(
        goal_description="test",
        nodes=[n1, n2],
        edges=[],
    )


class TestPDDLPlanSerializer:
    def test_topological_order(self):
        plan = _make_simple_plan()
        task = PlanningTask(
            task_id="t", domain_name="gripper",
            beliefs="", desire="",
        )
        serializer = PDDLPlanSerializer()
        actions = serializer.from_bdi_plan(plan, task)

        assert len(actions) == 2
        assert "move" in actions[0]
        assert "pick" in actions[1]

    def test_no_edges_preserves_node_order(self):
        plan = _make_no_edge_plan()
        task = PlanningTask(
            task_id="t", domain_name="test",
            beliefs="", desire="",
        )
        serializer = PDDLPlanSerializer()
        actions = serializer.from_bdi_plan(plan, task)

        assert len(actions) == 2
        # First node in plan.nodes should come first
        assert "move" in actions[0]
        assert "pick" in actions[1]

    def test_excludes_virtual_nodes(self):
        n1 = ActionNode(
            id="__START__", action_type="Virtual",
            description="virtual start", params={},
        )
        n2 = ActionNode(
            id="real", action_type="move",
            description="real action", params={"from": "a", "to": "b"},
        )
        plan = BDIPlan(
            goal_description="test",
            nodes=[n1, n2],
            edges=[DependencyEdge(
                source="__START__", target="real",
                relationship="sequential",
            )],
        )
        task = PlanningTask(task_id="t", domain_name="test", beliefs="", desire="")
        actions = PDDLPlanSerializer().from_bdi_plan(plan, task)

        assert len(actions) == 1
        assert "move" in actions[0]
