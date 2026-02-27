"""Tests for plan repair and canonicalization behaviors."""

from src.bdi_llm.schemas import BDIPlan, ActionNode, DependencyEdge
from src.bdi_llm.plan_repair import PlanRepairer, repair_and_verify, PlanCanonicalizer
from src.bdi_llm.verifier import PlanVerifier


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
