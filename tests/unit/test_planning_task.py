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
from src.bdi_llm.planner import BDIPlanner
from src.bdi_llm.planner.domain_spec import DomainSpec, extract_actions_from_pddl
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

OBFUSCATED_PROBLEM = textwrap.dedent("""\
    (define (problem instance-1)
      (:domain obfuscated_deceptive_logistics)
      (:objects o0 o1 o2 o3 o4 o5 o6 o7 o8 - object)
      (:init
        (cats o0)
        (cats o1)
        (stupendous o2)
        (stupendous o3)
        (sneeze o4)
        (sneeze o5)
        (texture o6)
        (texture o7)
        (collect o7 o3)
        (collect o6 o2)
        (spring o6)
        (spring o7)
        (hand o8)
        (next o8 o7)
        (next o1 o6))
      (:goal (next o8 o6)))
""")

LOGISTICS_DOMAIN = textwrap.dedent("""\
    (define (domain logistics-strips)
      (:action DRIVE-TRUCK
        :parameters (?truck ?loc-from ?loc-to ?city)
        :precondition (and)
        :effect (and))
      (:action FLY-AIRPLANE
        :parameters (?airplane ?loc-from ?loc-to)
        :precondition (and)
        :effect (and)))
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

    def test_planbench_style_prompt_when_domain_intro_provided(self):
        adapter = PDDLTaskAdapter(
            "obfuscated_deceptive_logistics",
            domain_context="ctx",
            domain_intro="I am playing with a set of objects.",
        )

        task = adapter.to_planning_task({
            "problem_text": OBFUSCATED_PROBLEM,
            "task_id": "planbench-style",
        })

        assert task.beliefs.startswith("I am playing with a set of objects.")
        assert "As initial conditions I have that" in task.beliefs
        assert "My goal is to have that" in task.desire
        assert "object_8" in task.beliefs
        assert "object_8" in task.desire
        assert " o8" not in task.beliefs
        assert " o8" not in task.desire
        assert task.domain_context == "ctx"


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

    def test_schema_order_accepts_hyphenated_pddl_names_for_underscore_params(self):
        plan = BDIPlan(
            goal_description="drive then fly",
            nodes=[
                ActionNode(
                    id="drive",
                    action_type="DRIVE-TRUCK",
                    description="drive truck",
                    params={
                        "truck": "t1",
                        "loc_from": "l1-0",
                        "loc_to": "l1-1",
                        "city": "c1",
                    },
                ),
                ActionNode(
                    id="fly",
                    action_type="FLY-AIRPLANE",
                    description="fly airplane",
                    params={
                        "airplane": "a0",
                        "loc_from": "l0-0",
                        "loc_to": "l1-0",
                    },
                ),
            ],
            edges=[
                DependencyEdge(source="drive", target="fly", relationship="sequential")
            ],
        )
        task = PlanningTask(task_id="t", domain_name="logistics", beliefs="", desire="")
        schema = {
            action["name"]: [param_name for param_name, _ptype in action["parameters"]]
            for action in extract_actions_from_pddl(LOGISTICS_DOMAIN)
        }

        actions = PDDLPlanSerializer(param_order_map=schema).from_bdi_plan(plan, task)

        assert actions == [
            "(DRIVE-TRUCK t1 l1-0 l1-1 c1)",
            "(FLY-AIRPLANE a0 l0-0 l1-0)",
        ]

    def test_schema_order_falls_back_to_positional_values_and_canonical_action_name(self):
        plan = BDIPlan(
            goal_description="drive truck",
            nodes=[
                ActionNode(
                    id="drive",
                    action_type="drive_truck",
                    description="drive truck",
                    params={
                        "vehicle": "t1",
                        "start": "l1-0",
                        "end": "l1-1",
                        "municipality": "c1",
                    },
                )
            ],
            edges=[],
        )
        task = PlanningTask(task_id="t", domain_name="logistics", beliefs="", desire="")
        schema = {
            action["name"]: [param_name for param_name, _ptype in action["parameters"]]
            for action in extract_actions_from_pddl(LOGISTICS_DOMAIN)
        }

        actions = PDDLPlanSerializer(param_order_map=schema).from_bdi_plan(plan, task)

        assert actions == ["(DRIVE-TRUCK t1 l1-0 l1-1 c1)"]

    def test_planbench_prompt_symbols_are_encoded_back_for_val(self):
        plan = BDIPlan(
            goal_description="move object",
            nodes=[
                ActionNode(
                    id="s1",
                    action_type="sip",
                    description="load object into airplane",
                    params={
                        "obj": "object_8",
                        "airplane": "object_1",
                        "loc": "object_7",
                    },
                )
            ],
            edges=[],
        )
        task = PlanningTask(
            task_id="t",
            domain_name="obfuscated_deceptive_logistics",
            beliefs="",
            desire="",
        )

        actions = PDDLPlanSerializer().from_bdi_plan(plan, task)

        assert actions == ["(sip o8 o1 o7)"]


class TestGenericConstraintValidation:
    def test_validate_action_constraints_normalizes_generic_action_and_param_names(self):
        spec = DomainSpec.from_pddl("logistics-strips", LOGISTICS_DOMAIN)
        planner = object.__new__(BDIPlanner)
        planner._domain_spec = spec

        plan = BDIPlan(
            goal_description="drive truck",
            nodes=[
                ActionNode(
                    id="drive",
                    action_type="drive_truck",
                    description="drive truck",
                    params={
                        "truck": "t1",
                        "loc_from": "l1-0",
                        "loc_to": "l1-1",
                        "city": "c1",
                    },
                )
            ],
            edges=[],
        )

        is_valid, message = BDIPlanner._validate_action_constraints(planner, plan)

        assert is_valid
        assert message == ""
