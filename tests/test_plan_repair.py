#!/usr/bin/env python3
"""
Test Auto-Repair System

Tests the plan repair functionality that fixes disconnected graphs.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.bdi_llm.schemas import BDIPlan, ActionNode, DependencyEdge
from src.bdi_llm.plan_repair import PlanRepairer, repair_and_verify, PlanCanonicalizer
from src.bdi_llm.verifier import PlanVerifier


def test_connected_plan():
    """Test that a connected plan passes through unchanged"""
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
        ]
    )

    result = PlanRepairer.repair(plan)

    assert result.success, f"Expected success, got: {result.errors}"
    assert result.original_valid, "Connected plan should be valid"
    assert len(result.repairs_applied) == 0, "No repairs needed"
    print("✅ test_connected_plan passed")


def test_disconnected_plan():
    """Test that a disconnected plan gets repaired"""
    plan = BDIPlan(
        goal_description="Test disconnected",
        nodes=[
            ActionNode(id="a1", action_type="Test", description="Island 1 - A"),
            ActionNode(id="a2", action_type="Test", description="Island 1 - B"),
            ActionNode(id="b1", action_type="Test", description="Island 2 - A"),
            ActionNode(id="b2", action_type="Test", description="Island 2 - B"),
        ],
        edges=[
            DependencyEdge(source="a1", target="a2"),  # Island 1
            DependencyEdge(source="b1", target="b2"),  # Island 2 (disconnected!)
        ]
    )

    result = PlanRepairer.repair(plan)

    assert result.success, f"Repair should succeed, errors: {result.errors}"
    assert not result.original_valid, "Original plan should be invalid"
    assert len(result.repairs_applied) > 0, "Repairs should be applied"

    # Verify repaired plan is valid
    G = result.repaired_plan.to_networkx()
    is_valid, errors = PlanVerifier.verify(G)
    assert is_valid, f"Repaired plan should be valid, errors: {errors}"

    # Check that virtual nodes were added
    node_ids = [n.id for n in result.repaired_plan.nodes]
    assert PlanRepairer.VIRTUAL_START in node_ids, "Virtual START should be added"
    assert PlanRepairer.VIRTUAL_END in node_ids, "Virtual END should be added"

    print("✅ test_disconnected_plan passed")


def test_parallel_tasks():
    """Test that parallel task structure (diamond pattern) is handled"""
    # This simulates "do A and B in parallel, then C"
    # Diamond pattern: A and B both go to C
    # This IS a valid connected DAG, so no repair should be needed
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
        ]
    )

    result = PlanRepairer.repair(plan)

    # This plan is actually valid (diamond pattern is a correct DAG)
    assert result.success, f"Repair should succeed, errors: {result.errors}"
    assert result.original_valid, "Diamond pattern is a valid connected DAG"
    print("✅ test_parallel_tasks passed (valid diamond pattern)")


def test_truly_disconnected_parallel():
    """Test truly disconnected parallel tasks that need repair"""
    # Two completely separate task chains - needs virtual nodes
    plan = BDIPlan(
        goal_description="Truly disconnected parallel",
        nodes=[
            ActionNode(id="a1", action_type="Chain1", description="Chain 1 - A"),
            ActionNode(id="a2", action_type="Chain1", description="Chain 1 - B"),
            ActionNode(id="b1", action_type="Chain2", description="Chain 2 - A"),
            ActionNode(id="b2", action_type="Chain2", description="Chain 2 - B"),
        ],
        edges=[
            DependencyEdge(source="a1", target="a2"),  # Chain 1
            DependencyEdge(source="b1", target="b2"),  # Chain 2 - completely separate
        ]
    )

    result = PlanRepairer.repair(plan)

    assert result.success, f"Repair should succeed, errors: {result.errors}"
    assert not result.original_valid, "Original should be invalid (disconnected)"

    # Check that virtual nodes were added
    node_ids = [n.id for n in result.repaired_plan.nodes]
    assert PlanRepairer.VIRTUAL_START in node_ids, "Virtual START should be added"
    assert PlanRepairer.VIRTUAL_END in node_ids, "Virtual END should be added"

    print("✅ test_truly_disconnected_parallel passed")


def test_canonicalizer():
    """Test plan canonicalization"""
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
        ]
    )

    canonical = PlanCanonicalizer.canonicalize(plan)

    # Check nodes are renamed in topological order
    node_ids = [n.id for n in canonical.nodes]
    assert node_ids == ["action_1", "action_2", "action_3"], f"Expected canonical IDs, got: {node_ids}"

    # Check edges are updated
    edge_pairs = [(e.source, e.target) for e in canonical.edges]
    assert ("action_1", "action_2") in edge_pairs
    assert ("action_2", "action_3") in edge_pairs

    print("✅ test_canonicalizer passed")


def test_convenience_function():
    """Test the repair_and_verify convenience function"""
    plan = BDIPlan(
        goal_description="Test convenience",
        nodes=[
            ActionNode(id="x", action_type="Test", description="X"),
            ActionNode(id="y", action_type="Test", description="Y"),
        ],
        edges=[]  # Disconnected!
    )

    repaired, is_valid, messages = repair_and_verify(plan)

    assert is_valid, "Should be valid after repair"
    assert len(messages) > 0, "Should have repair messages"

    print("✅ test_convenience_function passed")


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("Testing Auto-Repair System")
    print("="*60 + "\n")

    test_connected_plan()
    test_disconnected_plan()
    test_parallel_tasks()
    test_truly_disconnected_parallel()
    test_canonicalizer()
    test_convenience_function()

    print("\n" + "="*60)
    print("✅ All auto-repair tests passed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    run_all_tests()
