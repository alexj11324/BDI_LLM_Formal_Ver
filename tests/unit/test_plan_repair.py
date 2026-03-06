"""Tests for plan repair and canonicalization behaviors."""

from types import SimpleNamespace

from pyperplan import planner

from bdi_llm.schemas import BDIPlan, ActionNode, DependencyEdge
from bdi_llm.plan_repair import PlanRepairer, repair_and_verify, PlanCanonicalizer
from bdi_llm.verifier import PlanVerifier
from scripts.evaluation.planbench_utils.bdi_to_pddl import bdi_to_pddl_actions
from src.bdi_llm.dynamic_replanner.symbolic_fallback import SymbolicFallbackPlanner


def test_connected_plan_remains_unchanged():
    plan = BDIPlan(
        goal_description="Test goal",
        nodes=[
            ActionNode(id="a", action_type="Test", description="Action A"),
            ActionNode(id="b", action_type="Test", description="Action B"),
            ActionNode(id="c", action_type="Test", description="Action C"),
        ],
        edges=[
            DependencyEdge(source="a", target="b"),
            DependencyEdge(source="b", target="c"),
        ],
    )

    result = PlanRepairer.repair(plan)

    assert result.success
    assert result.original_valid
    assert result.repairs_applied == []


def test_disconnected_plan_gets_repaired_and_validated():
    plan = BDIPlan(
        goal_description="Test disconnected",
        nodes=[
            ActionNode(id="a1", action_type="Test", description="Island 1 - A"),
            ActionNode(id="a2", action_type="Test", description="Island 1 - B"),
            ActionNode(id="b1", action_type="Test", description="Island 2 - A"),
            ActionNode(id="b2", action_type="Test", description="Island 2 - B"),
        ],
        edges=[
            DependencyEdge(source="a1", target="a2"),
            DependencyEdge(source="b1", target="b2"),
        ],
    )

    result = PlanRepairer.repair(plan)

    assert result.success
    assert not result.original_valid
    assert result.repairs_applied

    is_valid, errors = PlanVerifier.verify(result.repaired_plan.to_networkx())
    assert is_valid, errors

    node_ids = [n.id for n in result.repaired_plan.nodes]
    assert PlanRepairer.VIRTUAL_START in node_ids
    assert PlanRepairer.VIRTUAL_END in node_ids


def test_parallel_diamond_pattern_is_already_valid():
    plan = BDIPlan(
        goal_description="Parallel tasks",
        nodes=[
            ActionNode(id="task_a", action_type="Parallel", description="Task A"),
            ActionNode(id="task_b", action_type="Parallel", description="Task B"),
            ActionNode(id="sync", action_type="Sync", description="Synchronization point"),
        ],
        edges=[
            DependencyEdge(source="task_a", target="sync"),
            DependencyEdge(source="task_b", target="sync"),
        ],
    )

    result = PlanRepairer.repair(plan)

    assert result.success
    assert result.original_valid


def test_canonicalizer_renames_nodes_in_topological_order():
    plan = BDIPlan(
        goal_description="Test canonicalization",
        nodes=[
            ActionNode(id="z", action_type="Test", description="Should be last"),
            ActionNode(id="a", action_type="Test", description="Should be first"),
            ActionNode(id="m", action_type="Test", description="Should be middle"),
        ],
        edges=[
            DependencyEdge(source="a", target="m"),
            DependencyEdge(source="m", target="z"),
        ],
    )

    canonical = PlanCanonicalizer.canonicalize(plan)

    assert [n.id for n in canonical.nodes] == ["action_1", "action_2", "action_3"]
    edge_pairs = {(e.source, e.target) for e in canonical.edges}
    assert ("action_1", "action_2") in edge_pairs
    assert ("action_2", "action_3") in edge_pairs


def test_repair_and_verify_convenience_function_repairs_plan():
    plan = BDIPlan(
        goal_description="Test convenience",
        nodes=[
            ActionNode(id="x", action_type="Test", description="X"),
            ActionNode(id="y", action_type="Test", description="Y"),
        ],
        edges=[],
    )

    repaired, is_valid, messages = repair_and_verify(plan)

    assert is_valid
    assert messages
    assert isinstance(repaired, BDIPlan)


def test_repair_reuses_existing_virtual_nodes_without_duplication():
    """Regression: inputs already containing virtual IDs should not get duplicated nodes."""
    plan = BDIPlan(
        goal_description="Reuse virtual nodes",
        nodes=[
            ActionNode(id=PlanRepairer.VIRTUAL_START, action_type="Virtual", description="Existing start"),
            ActionNode(id=PlanRepairer.VIRTUAL_END, action_type="Virtual", description="Existing end"),
            ActionNode(id="a", action_type="Test", description="A"),
            ActionNode(id="b", action_type="Test", description="B"),
        ],
        edges=[DependencyEdge(source="a", target=PlanRepairer.VIRTUAL_END)],
    )

    result = PlanRepairer.repair(plan)
    assert result.success

    repaired_ids = [node.id for node in result.repaired_plan.nodes]
    assert repaired_ids.count(PlanRepairer.VIRTUAL_START) == 1
    assert repaired_ids.count(PlanRepairer.VIRTUAL_END) == 1


def test_simple_cycle_is_broken():
    """Test that a simple 3-node cycle A -> B -> C -> A is broken."""
    plan = BDIPlan(
        goal_description="Test cycle",
        nodes=[
            ActionNode(id="a", action_type="Test", description="A"),
            ActionNode(id="b", action_type="Test", description="B"),
            ActionNode(id="c", action_type="Test", description="C"),
        ],
        edges=[
            DependencyEdge(source="a", target="b"),
            DependencyEdge(source="b", target="c"),
            DependencyEdge(source="c", target="a"),  # Creates cycle
        ],
    )

    result = PlanRepairer.repair(plan)

    assert result.success
    assert "Broke cycles to convert graph to DAG" in result.repairs_applied

    # Verify the repaired plan is a DAG
    is_valid, errors = PlanVerifier.verify(result.repaired_plan.to_networkx())
    assert is_valid, f"Repaired plan has errors: {errors}"

    # Verify one edge was removed (breaking the cycle)
    assert len(result.repaired_plan.edges) == 2


def test_complex_cycle_with_multiple_paths():
    """Test cycle breaking with parallel paths that merge and cycle back."""
    plan = BDIPlan(
        goal_description="Complex cycle",
        nodes=[
            ActionNode(id="start", action_type="Start", description="Start"),
            ActionNode(id="a", action_type="Test", description="A"),
            ActionNode(id="b", action_type="Test", description="B"),
            ActionNode(id="c", action_type="Test", description="C"),
            ActionNode(id="end", action_type="End", description="End"),
        ],
        edges=[
            DependencyEdge(source="start", target="a"),
            DependencyEdge(source="start", target="b"),
            DependencyEdge(source="a", target="c"),
            DependencyEdge(source="b", target="c"),
            DependencyEdge(source="c", target="a"),  # Back edge creating cycle
            DependencyEdge(source="c", target="end"),
        ],
    )

    result = PlanRepairer.repair(plan)

    assert result.success
    assert "Broke cycles to convert graph to DAG" in result.repairs_applied

    # Verify the repaired plan is a DAG
    is_valid, errors = PlanVerifier.verify(result.repaired_plan.to_networkx())
    assert is_valid, f"Repaired plan has errors: {errors}"


def test_logistics_style_long_cycle():
    """Test breaking a long cycle similar to logistics domain failures."""
    plan = BDIPlan(
        goal_description="Logistics delivery",
        nodes=[
            ActionNode(id="load_p3", action_type="Load", description="Load package 3"),
            ActionNode(id="fly_a1", action_type="Fly", description="Fly airplane"),
            ActionNode(id="unload_p3", action_type="Unload", description="Unload package 3"),
            ActionNode(id="drive_t0", action_type="Drive", description="Drive truck"),
            ActionNode(id="load_p0", action_type="Load", description="Load package 0"),
            ActionNode(id="drive_t0_2", action_type="Drive", description="Drive truck again"),
            ActionNode(id="load_p1", action_type="Load", description="Load package 1"),
        ],
        edges=[
            DependencyEdge(source="load_p3", target="fly_a1"),
            DependencyEdge(source="fly_a1", target="unload_p3"),
            DependencyEdge(source="unload_p3", target="drive_t0"),
            DependencyEdge(source="drive_t0", target="load_p0"),
            DependencyEdge(source="load_p0", target="drive_t0_2"),
            DependencyEdge(source="drive_t0_2", target="load_p1"),
            DependencyEdge(source="load_p1", target="load_p3"),  # Back edge
        ],
    )

    result = PlanRepairer.repair(plan)

    assert result.success
    assert "Broke cycles to convert graph to DAG" in result.repairs_applied

    # Verify the repaired plan is a DAG
    is_valid, errors = PlanVerifier.verify(result.repaired_plan.to_networkx())
    assert is_valid, f"Repaired plan has errors: {errors}"

    # Verify the back edge was removed (7 edges -> 6 edges)
    assert len(result.repaired_plan.edges) == 6


def test_cycle_and_disconnected_combined():
    """Test that cycles are broken before connecting disconnected subgraphs."""
    plan = BDIPlan(
        goal_description="Cycle + disconnected",
        nodes=[
            # Component 1: has a cycle
            ActionNode(id="a1", action_type="Test", description="A1"),
            ActionNode(id="a2", action_type="Test", description="A2"),
            ActionNode(id="a3", action_type="Test", description="A3"),
            # Component 2: linear chain
            ActionNode(id="b1", action_type="Test", description="B1"),
            ActionNode(id="b2", action_type="Test", description="B2"),
        ],
        edges=[
            # Component 1: cycle
            DependencyEdge(source="a1", target="a2"),
            DependencyEdge(source="a2", target="a3"),
            DependencyEdge(source="a3", target="a1"),
            # Component 2: linear (disconnected from component 1)
            DependencyEdge(source="b1", target="b2"),
        ],
    )

    result = PlanRepairer.repair(plan)

    assert result.success
    repairs = result.repairs_applied
    assert "Broke cycles to convert graph to DAG" in repairs
    assert "Connected disconnected subgraphs" in str(repairs)

    # Verify the repaired plan is a DAG and connected
    is_valid, errors = PlanVerifier.verify(result.repaired_plan.to_networkx())
    assert is_valid, f"Repaired plan has errors: {errors}"


def test_dag_passes_through_unchanged():
    """Test that a valid DAG is not modified by cycle breaking."""
    plan = BDIPlan(
        goal_description="Valid DAG",
        nodes=[
            ActionNode(id="a", action_type="Test", description="A"),
            ActionNode(id="b", action_type="Test", description="B"),
            ActionNode(id="c", action_type="Test", description="C"),
            ActionNode(id="d", action_type="Test", description="D"),
        ],
        edges=[
            DependencyEdge(source="a", target="b"),
            DependencyEdge(source="a", target="c"),
            DependencyEdge(source="b", target="d"),
            DependencyEdge(source="c", target="d"),
        ],
    )

    result = PlanRepairer.repair(plan)

    assert result.success
    assert result.original_valid
    assert result.repairs_applied == []


def test_cycle_breaking_preserves_non_cycle_feeder_edges():
    """
    Regression: DFS cycle breaking should remove only true back-edges.

    In this graph, `x -> b` is a feeder edge into a cyclic component and must
    not be removed when breaking the `b <-> c` cycle.
    """
    plan = BDIPlan(
        goal_description="Preserve feeder edge",
        nodes=[
            ActionNode(id="a", action_type="Test", description="A"),
            ActionNode(id="b", action_type="Test", description="B"),
            ActionNode(id="c", action_type="Test", description="C"),
            ActionNode(id="x", action_type="Test", description="X"),
        ],
        edges=[
            DependencyEdge(source="a", target="b"),
            DependencyEdge(source="b", target="c"),
            DependencyEdge(source="c", target="b"),  # Cycle edge
            DependencyEdge(source="x", target="b"),  # Non-cycle feeder edge
        ],
    )

    result = PlanRepairer.repair(plan)

    assert result.success
    repaired_edges = {(edge.source, edge.target) for edge in result.repaired_plan.edges}

    # Non-cycle feeder edge should be preserved.
    assert ("x", "b") in repaired_edges
    # Exactly one edge from the 2-cycle should remain.
    assert len({("b", "c"), ("c", "b")} & repaired_edges) == 1


def test_bdi_plan_model_validate_accepts_common_aliases_and_missing_ids():
    plan = BDIPlan.model_validate(
        {
            "nodes": [
                {
                    "type": "load-truck",
                    "params": {"obj": "p1", "truck": "t0", "loc": "l0-0"},
                    "description": "Load package into truck",
                },
                {
                    "action": "drive-truck",
                    "params": {
                        "truck": "t0",
                        "from": "l0-0",
                        "to": "l0-1",
                        "city": "c0",
                    },
                    "description": "Drive truck to the airport",
                },
            ],
            "edges": [{"from": "step_1", "to": "step_2"}],
        }
    )

    assert plan.goal_description == "Generated plan"
    assert [node.id for node in plan.nodes] == ["step_1", "step_2"]
    assert [node.action_type for node in plan.nodes] == ["load-truck", "drive-truck"]
    assert [(edge.source, edge.target) for edge in plan.edges] == [("step_1", "step_2")]


def test_bdi_plan_missing_edges_key_linearizes_node_order():
    plan = BDIPlan.model_validate(
        {
            "goal_description": "Deliver package",
            "nodes": [
                {
                    "id": "n1",
                    "action_type": "load-truck",
                    "params": {"obj": "p1", "truck": "t0", "loc": "l0-0"},
                    "description": "Load",
                },
                {
                    "id": "n2",
                    "action_type": "drive-truck",
                    "params": {
                        "truck": "t0",
                        "from": "l0-0",
                        "to": "l0-1",
                        "city": "c0",
                    },
                    "description": "Drive",
                },
                {
                    "id": "n3",
                    "action_type": "unload-truck",
                    "params": {"obj": "p1", "truck": "t0", "loc": "l0-1"},
                    "description": "Unload",
                },
            ],
        }
    )

    assert [(edge.source, edge.target) for edge in plan.edges] == [
        ("n1", "n2"),
        ("n2", "n3"),
    ]


def test_bdi_to_pddl_actions_accepts_raw_pddl_action_type():
    plan = BDIPlan(
        goal_description="Fallback plan",
        nodes=[
            ActionNode(
                id="fallback_0",
                action_type="(LOAD-TRUCK p1 t0 l0-0)",
                params={},
                description="Raw symbolic fallback action",
            )
        ],
        edges=[],
    )

    assert bdi_to_pddl_actions(plan, domain="logistics") == ["(LOAD-TRUCK p1 t0 l0-0)"]


def test_symbolic_fallback_uses_callable_pyperplan_api(tmp_path, monkeypatch):
    domain_file = tmp_path / "domain.pddl"
    problem_file = tmp_path / "problem.pddl"

    domain_file.write_text("(define (domain dummy))", encoding="utf-8")
    problem_file.write_text(
        """
(define (problem dummy-problem)
  (:domain dummy)
  (:init
    (at p1 l0-0)
  )
  (:goal
    (and (delivered p1))
  )
)
""".strip(),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def fake_search_plan(domain_path, problem_path, search, heuristic_class, use_preferred_ops=False):
        captured["domain_path"] = domain_path
        captured["problem_path"] = problem_path
        captured["search"] = search
        captured["heuristic_class"] = heuristic_class
        captured["use_preferred_ops"] = use_preferred_ops
        return [SimpleNamespace(name="load-truck p1 t0 l0-0")]

    monkeypatch.setattr(planner, "search_plan", fake_search_plan)

    plan = SymbolicFallbackPlanner.generate_fallback_plan(
        str(domain_file),
        str(problem_file),
        {"(at p1 l0-0)"},
    )

    assert plan is not None
    assert captured["domain_path"] == str(domain_file)
    assert captured["search"] is planner.SEARCHES["astar"]
    assert captured["heuristic_class"] is planner.HEURISTICS["hmax"]
    assert bdi_to_pddl_actions(plan, domain="logistics") == ["(load-truck p1 t0 l0-0)"]


def test_symbolic_fallback_preserves_single_parenthesized_action_names(tmp_path, monkeypatch):
    domain_file = tmp_path / "domain.pddl"
    problem_file = tmp_path / "problem.pddl"

    domain_file.write_text("(define (domain dummy))", encoding="utf-8")
    problem_file.write_text(
        """
(define (problem dummy-problem)
  (:domain dummy)
  (:init
    (at p1 l0-0)
  )
  (:goal
    (and (delivered p1))
  )
)
""".strip(),
        encoding="utf-8",
    )

    def fake_search_plan(domain_path, problem_path, search, heuristic_class, use_preferred_ops=False):
        return [SimpleNamespace(name="(drive-truck t0 l0-0 l0-1 c0)")]

    monkeypatch.setattr(planner, "search_plan", fake_search_plan)

    plan = SymbolicFallbackPlanner.generate_fallback_plan(
        str(domain_file),
        str(problem_file),
        {"(at p1 l0-0)"},
    )

    assert plan is not None
    assert plan.nodes[0].action_type == "(drive-truck t0 l0-0 l0-1 c0)"


def test_symbolic_fallback_records_error_for_invalid_state(tmp_path):
    domain_file = tmp_path / "domain.pddl"
    problem_file = tmp_path / "problem.pddl"

    domain_file.write_text("(define (domain dummy))", encoding="utf-8")
    problem_file.write_text(
        """
(define (problem dummy-problem)
  (:domain dummy)
  (:init
    (at p1 l0-0)
  )
  (:goal
    (and (delivered p1))
  )
)
""".strip(),
        encoding="utf-8",
    )

    plan = SymbolicFallbackPlanner.generate_fallback_plan(
        str(domain_file),
        str(problem_file),
        {"(at ?pkg l0-0)"},
    )

    assert plan is None
    assert SymbolicFallbackPlanner.last_error == (
        "Fallback state is empty or contains no valid ground propositions."
    )
