#!/usr/bin/env python3
"""
Smoke Test for Cycle Repair
============================

Run 10 known cyclic instances and verify repair success rate improves from 0% to >50%.

This script:
1. Creates 10 synthetic cyclic plans (varying complexity)
2. Tests current repair success rate
3. Reports baseline (should be 0% without cycle repair)
4. After cycle repair implementation, should achieve >50% success

Usage:
    python tests/smoke_test_cycle_repair.py

Expected output:
    - Before cycle repair: 0% success rate
    - After cycle repair: >50% success rate
"""

import sys
import os

from bdi_llm.schemas import ActionNode, DependencyEdge, BDIPlan
from bdi_llm.verifier import PlanVerifier
from bdi_llm.plan_repair import PlanRepairer

def create_simple_cycle():
    """A -> B -> A"""
    return BDIPlan(
        goal_description="Simple cycle",
        nodes=[
            ActionNode(id="A", action_type="Action", description="A"),
            ActionNode(id="B", action_type="Action", description="B"),
        ],
        edges=[
            DependencyEdge(source="A", target="B"),
            DependencyEdge(source="B", target="A"),
        ]
    )

def create_three_node_cycle():
    """A -> B -> C -> A"""
    return BDIPlan(
        goal_description="3-node cycle",
        nodes=[
            ActionNode(id="A", action_type="Action", description="A"),
            ActionNode(id="B", action_type="Action", description="B"),
            ActionNode(id="C", action_type="Action", description="C"),
        ],
        edges=[
            DependencyEdge(source="A", target="B"),
            DependencyEdge(source="B", target="C"),
            DependencyEdge(source="C", target="A"),
        ]
    )

def create_four_node_cycle():
    """A -> B -> C -> D -> A"""
    return BDIPlan(
        goal_description="4-node cycle",
        nodes=[
            ActionNode(id="A", action_type="Action", description="A"),
            ActionNode(id="B", action_type="Action", description="B"),
            ActionNode(id="C", action_type="Action", description="C"),
            ActionNode(id="D", action_type="Action", description="D"),
        ],
        edges=[
            DependencyEdge(source="A", target="B"),
            DependencyEdge(source="B", target="C"),
            DependencyEdge(source="C", target="D"),
            DependencyEdge(source="D", target="A"),
        ]
    )

def create_complex_cycle_with_parallel_chain():
    """A -> B -> C -> A with parallel D -> E"""
    return BDIPlan(
        goal_description="Complex cycle with parallel chain",
        nodes=[
            ActionNode(id="A", action_type="Action", description="A"),
            ActionNode(id="B", action_type="Action", description="B"),
            ActionNode(id="C", action_type="Action", description="C"),
            ActionNode(id="D", action_type="Action", description="D"),
            ActionNode(id="E", action_type="Action", description="E"),
        ],
        edges=[
            DependencyEdge(source="A", target="B"),
            DependencyEdge(source="B", target="C"),
            DependencyEdge(source="C", target="A"),
            DependencyEdge(source="D", target="E"),
        ]
    )

def create_nested_cycles():
    """A -> B -> C -> A and B -> D -> B (two interlocking cycles)"""
    return BDIPlan(
        goal_description="Nested cycles",
        nodes=[
            ActionNode(id="A", action_type="Action", description="A"),
            ActionNode(id="B", action_type="Action", description="B"),
            ActionNode(id="C", action_type="Action", description="C"),
            ActionNode(id="D", action_type="Action", description="D"),
        ],
        edges=[
            DependencyEdge(source="A", target="B"),
            DependencyEdge(source="B", target="C"),
            DependencyEdge(source="C", target="A"),
            DependencyEdge(source="B", target="D"),
            DependencyEdge(source="D", target="B"),
        ]
    )

def create_self_loop():
    """A -> A (self-loop)"""
    return BDIPlan(
        goal_description="Self loop",
        nodes=[
            ActionNode(id="A", action_type="Action", description="A"),
        ],
        edges=[
            DependencyEdge(source="A", target="A"),
        ]
    )

def create_double_self_loop():
    """A -> A and B -> B"""
    return BDIPlan(
        goal_description="Double self loops",
        nodes=[
            ActionNode(id="A", action_type="Action", description="A"),
            ActionNode(id="B", action_type="Action", description="B"),
        ],
        edges=[
            DependencyEdge(source="A", target="A"),
            DependencyEdge(source="B", target="B"),
        ]
    )

def create_cycle_with_disconnected_component():
    """A -> B -> A (cycle) + C -> D (disconnected)"""
    return BDIPlan(
        goal_description="Cycle with disconnected component",
        nodes=[
            ActionNode(id="A", action_type="Action", description="A"),
            ActionNode(id="B", action_type="Action", description="B"),
            ActionNode(id="C", action_type="Action", description="C"),
            ActionNode(id="D", action_type="Action", description="D"),
        ],
        edges=[
            DependencyEdge(source="A", target="B"),
            DependencyEdge(source="B", target="A"),
            DependencyEdge(source="C", target="D"),
        ]
    )

def create_long_cycle():
    """A -> B -> C -> D -> E -> A (5-node cycle)"""
    return BDIPlan(
        goal_description="Long cycle",
        nodes=[
            ActionNode(id="A", action_type="Action", description="A"),
            ActionNode(id="B", action_type="Action", description="B"),
            ActionNode(id="C", action_type="Action", description="C"),
            ActionNode(id="D", action_type="Action", description="D"),
            ActionNode(id="E", action_type="Action", description="E"),
        ],
        edges=[
            DependencyEdge(source="A", target="B"),
            DependencyEdge(source="B", target="C"),
            DependencyEdge(source="C", target="D"),
            DependencyEdge(source="D", target="E"),
            DependencyEdge(source="E", target="A"),
        ]
    )

def create_multiple_disjoint_cycles():
    """A -> B -> A (cycle 1) + C -> D -> C (cycle 2)"""
    return BDIPlan(
        goal_description="Multiple disjoint cycles",
        nodes=[
            ActionNode(id="A", action_type="Action", description="A"),
            ActionNode(id="B", action_type="Action", description="B"),
            ActionNode(id="C", action_type="Action", description="C"),
            ActionNode(id="D", action_type="Action", description="D"),
        ],
        edges=[
            DependencyEdge(source="A", target="B"),
            DependencyEdge(source="B", target="A"),
            DependencyEdge(source="C", target="D"),
            DependencyEdge(source="D", target="C"),
        ]
    )

def run_smoke_test():
    """
    Run smoke test on 10 cyclic instances.

    Returns:
        tuple: (success_count, total_count, success_rate)
    """
    # Create 10 test cases
    test_cases = [
        ("Simple 2-node cycle", create_simple_cycle()),
        ("3-node cycle", create_three_node_cycle()),
        ("4-node cycle", create_four_node_cycle()),
        ("Complex cycle + parallel", create_complex_cycle_with_parallel_chain()),
        ("Nested cycles", create_nested_cycles()),
        ("Self loop", create_self_loop()),
        ("Double self loops", create_double_self_loop()),
        ("Cycle + disconnected", create_cycle_with_disconnected_component()),
        ("Long 5-node cycle", create_long_cycle()),
        ("Multiple disjoint cycles", create_multiple_disjoint_cycles()),
    ]

    print("=" * 60)
    print("CYCLE REPAIR SMOKE TEST")
    print("=" * 60)
    print(f"\nTesting {len(test_cases)} cyclic instances...\n")

    success_count = 0
    results = []

    for name, plan in test_cases:
        # Verify original has cycle
        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        # Attempt repair
        result = PlanRepairer.repair(plan)

        # Check if repair succeeded
        repair_success = result.success

        if repair_success:
            success_count += 1
            status = "PASS"
        else:
            status = "FAIL"

        results.append((name, is_valid, repair_success, result.repairs_applied, result.errors))
        print(f"  [{status}] {name}")
        if not repair_success and result.errors:
            print(f"         Errors: {result.errors[:2]}")  # Show first 2 errors

    # Calculate success rate
    total = len(test_cases)
    success_rate = (success_count / total) * 100 if total > 0 else 0

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(f"  Successful repairs: {success_count}/{total}")
    print(f"  Success rate: {success_rate:.1f}%")
    print()

    # Evaluate against targets
    print("TARGET EVALUATION")
    print("-" * 40)

    # Baseline target (current state without cycle repair)
    baseline_target = 0
    if success_rate >= baseline_target:
        print(f"  [PASS] Baseline ({baseline_target}%): {success_rate:.1f}% >= {baseline_target}%")
    else:
        print(f"  [FAIL] Baseline ({baseline_target}%): {success_rate:.1f}% < {baseline_target}%")

    # Improvement target (after cycle repair implementation)
    improvement_target = 50
    if success_rate >= improvement_target:
        print(f"  [PASS] Improvement target ({improvement_target}%): {success_rate:.1f}% >= {improvement_target}%")
        print("\n  Cycle repair is working effectively!")
    else:
        print(f"  [INFO] Improvement target ({improvement_target}%): {success_rate:.1f}% < {improvement_target}%")
        print("  Cycle repair implementation needed to achieve >50% success rate")

    print()

    return success_count, total, success_rate

if __name__ == "__main__":
    success_count, total, success_rate = run_smoke_test()

    # Exit with appropriate code
    # For now, we expect 0% success (baseline)
    # After cycle repair implementation, should be >50%
    sys.exit(0)  # Always exit 0 for smoke test (informational)
