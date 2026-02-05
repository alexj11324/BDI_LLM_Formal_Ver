#!/usr/bin/env python3
"""
Quick Fix for Parallel Task Problem
====================================

Implements Phase 1 improvements from SOTA_TRAINING_METHODS.md:
1. Few-shot examples with fork-join patterns
2. Post-hoc graph repair for disconnected components

Usage:
    python scripts/quick_fix_parallel_tasks.py --demo
    python scripts/quick_fix_parallel_tasks.py --test

Author: Based on SDPO + TTRL research
Date: 2026-02-03
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bdi_llm.schemas import ActionNode, DependencyEdge, BDIPlan
from src.bdi_llm.verifier import PlanVerifier
import networkx as nx
import dspy


def verify_plan(plan: BDIPlan):
    """Wrapper for PlanVerifier to work with BDIPlan objects"""
    graph = plan.to_networkx()
    return PlanVerifier.verify(graph)


# ============================================================================
# FEW-SHOT EXAMPLES (Inspired by TTRL majority voting patterns)
# ============================================================================

FORK_JOIN_EXAMPLE = dspy.Example(
    beliefs="""
    - Printer is available and has paper loaded
    - Email server is accessible
    - Document is ready to be sent
    """,
    desire="Print the document and send it via email simultaneously to save time",
    rationale="""
    For PARALLEL tasks, we MUST use a fork-join pattern to maintain graph connectivity:

    Structure:
        START
        ├─→ Task A (Print)
        └─→ Task B (Email)
        Both A and B then connect to:
        END

    This creates a DIAMOND pattern that is:
    - Weakly connected (all nodes reachable)
    - Acyclic (no circular dependencies)
    - Parallel (A and B can execute simultaneously)
    """,
    plan=BDIPlan(
        goal_description="Complete document distribution via parallel channels",
        nodes=[
            ActionNode(
                id="START",
                action_type="initialize",
                params={},
                description="Initialize parallel task execution"
            ),
            ActionNode(
                id="print_doc",
                action_type="print_action",
                params={"printer": "default", "copies": 1},
                description="Print document using available printer"
            ),
            ActionNode(
                id="email_doc",
                action_type="email_action",
                params={"recipient": "user@example.com", "attachment": "document.pdf"},
                description="Send document via email"
            ),
            ActionNode(
                id="END",
                action_type="finalize",
                params={},
                description="Confirm both parallel tasks completed"
            )
        ],
        edges=[
            # Fork: START branches to both parallel tasks
            DependencyEdge(source="START", target="print_doc"),
            DependencyEdge(source="START", target="email_doc"),

            # Join: Both tasks converge at END
            DependencyEdge(source="print_doc", target="END"),
            DependencyEdge(source="email_doc", target="END")
        ]
    )
)


COMPLEX_PARALLEL_EXAMPLE = dspy.Example(
    beliefs="""
    - Database connection is established
    - User authentication service is running
    - Cache server is available
    """,
    desire="Fetch user profile from database and update cache simultaneously after authentication",
    plan=BDIPlan(
        goal_description="Optimize user data retrieval with parallel caching",
        nodes=[
            ActionNode(id="authenticate", action_type="auth", params={}, description="Verify user credentials"),
            ActionNode(id="fetch_db", action_type="database_query", params={}, description="Retrieve profile from database"),
            ActionNode(id="update_cache", action_type="cache_write", params={}, description="Write profile to cache"),
            ActionNode(id="return_profile", action_type="response", params={}, description="Return user profile to client")
        ],
        edges=[
            # Sequential: authenticate first
            DependencyEdge(source="authenticate", target="fetch_db"),
            DependencyEdge(source="authenticate", target="update_cache"),

            # Join: both parallel tasks complete before response
            DependencyEdge(source="fetch_db", target="return_profile"),
            DependencyEdge(source="update_cache", target="return_profile")
        ]
    )
)


# ============================================================================
# POST-HOC GRAPH REPAIR (Inspired by AutoRocq error-driven refinement)
# ============================================================================

def auto_repair_disconnected_graph(plan: BDIPlan) -> tuple[BDIPlan, bool]:
    """
    Automatically repairs disconnected components by inserting virtual START/END nodes.

    This is a fallback mechanism when few-shot examples fail to prevent the issue.
    Similar to AutoRocq's dynamic context search + repair strategy.

    Args:
        plan: BDIPlan that may have disconnected components

    Returns:
        (repaired_plan, was_repaired): Tuple of repaired plan and boolean flag
    """
    G = plan.to_networkx()

    # Check if repair is needed
    if nx.is_weakly_connected(G):
        return plan, False  # No repair needed

    print("⚠️  GRAPH REPAIR TRIGGERED: Disconnected components detected")

    # Find all weakly connected components
    components = list(nx.weakly_connected_components(G))
    print(f"   Found {len(components)} disconnected components")

    # Create virtual START node if doesn't exist
    has_start = any(node.id == "START" for node in plan.nodes)
    if not has_start:
        plan.nodes.insert(0, ActionNode(
            id="START",
            action_type="initialize",
            params={},
            description="[AUTO-GENERATED] Virtual start node for graph connectivity"
        ))

    # Create virtual END node if doesn't exist
    has_end = any(node.id == "END" for node in plan.nodes)
    if not has_end:
        plan.nodes.append(ActionNode(
            id="END",
            action_type="finalize",
            params={},
            description="[AUTO-GENERATED] Virtual end node for graph connectivity"
        ))

    # Rebuild graph to include new nodes
    G = plan.to_networkx()
    components = list(nx.weakly_connected_components(G))

    # For each component (excluding START/END themselves)
    for component in components:
        component_nodes = list(component)

        # Skip if this component only contains START or END
        if component_nodes == ["START"] or component_nodes == ["END"]:
            continue

        # Find nodes with no predecessors (entry points)
        entry_nodes = [
            node for node in component_nodes
            if G.in_degree(node) == 0 and node not in ["START", "END"]
        ]

        # Find nodes with no successors (exit points)
        exit_nodes = [
            node for node in component_nodes
            if G.out_degree(node) == 0 and node not in ["START", "END"]
        ]

        # Connect START to all entry points (fork)
        for entry in entry_nodes:
            edge = DependencyEdge(source="START", target=entry)
            if edge not in plan.edges:
                plan.edges.append(edge)
                print(f"   Added fork edge: START → {entry}")

        # Connect all exit points to END (join)
        for exit_point in exit_nodes:
            edge = DependencyEdge(source=exit_point, target="END")
            if edge not in plan.edges:
                plan.edges.append(edge)
                print(f"   Added join edge: {exit_point} → END")

    print("✅ Graph repair completed\n")
    return plan, True


# ============================================================================
# ENHANCED PLANNER WITH SDPO-STYLE SELF-CORRECTION
# ============================================================================

class EnhancedPlanner:
    """
    Planner with built-in few-shot examples and automatic repair.

    Combines:
    - TTRL-style few-shot patterns (fork-join examples)
    - SDPO-style self-distillation (implicit via DSPy examples)
    - AutoRocq-style error-driven repair (post-hoc graph repair)
    """

    def __init__(self, base_planner):
        self.base_planner = base_planner
        self.few_shot_examples = [FORK_JOIN_EXAMPLE, COMPLEX_PARALLEL_EXAMPLE]

    def generate(self, beliefs: str, desire: str, enable_auto_repair: bool = True) -> BDIPlan:
        """
        Generate a plan with automatic quality improvements.

        Args:
            beliefs: Current state/beliefs
            desire: Goal to achieve
            enable_auto_repair: Whether to apply post-hoc graph repair

        Returns:
            Validated BDIPlan (or best-effort if repair fails)
        """
        # Step 1: Generate initial plan (with few-shot examples in context)
        # Note: In production, inject few_shot_examples into DSPy predictor
        plan = self.base_planner(beliefs=beliefs, desire=desire).plan

        # Step 2: Verify initial plan
        is_valid, errors = verify_plan(plan)

        if is_valid:
            print("✅ Plan passed verification on first attempt")
            return plan

        print(f"❌ Initial plan failed: {errors}\n")

        # Step 3: Attempt auto-repair if enabled
        if enable_auto_repair and "not weakly connected" in str(errors):
            plan, was_repaired = auto_repair_disconnected_graph(plan)

            if was_repaired:
                # Re-verify repaired plan
                is_valid, errors = verify_plan(plan)

                if is_valid:
                    print("✅ Repaired plan passed verification")
                    return plan
                else:
                    print(f"⚠️  Repaired plan still has issues: {errors}")

        # Step 4: Return best-effort result
        print("⚠️  Returning plan with warnings (manual review recommended)")
        return plan


# ============================================================================
# DEMO & TEST FUNCTIONS
# ============================================================================

def demo_parallel_task_fix():
    """Demonstrates the parallel task fix using mock planner."""
    print("=" * 70)
    print("DEMO: Parallel Task Fix with Few-Shot + Auto-Repair")
    print("=" * 70)
    print()

    # Simulate a plan with disconnected components (the bug case)
    buggy_plan = BDIPlan(
        goal_description="Print and email document in parallel",
        nodes=[
            ActionNode(id="print", action_type="action", params={}, description="Print document"),
            ActionNode(id="email", action_type="action", params={}, description="Email document")
        ],
        edges=[]  # No edges → disconnected!
    )

    print("BEFORE REPAIR:")
    print(f"  Nodes: {[n.id for n in buggy_plan.nodes]}")
    print(f"  Edges: {[(e.source, e.target) for e in buggy_plan.edges]}")

    is_valid, errors = verify_plan(buggy_plan)
    print(f"  Valid: {is_valid}")
    print(f"  Errors: {errors}\n")

    # Apply repair
    repaired_plan, was_repaired = auto_repair_disconnected_graph(buggy_plan)

    print("AFTER REPAIR:")
    print(f"  Nodes: {[n.id for n in repaired_plan.nodes]}")
    print(f"  Edges: {[(e.source, e.target) for e in repaired_plan.edges]}")

    is_valid, errors = verify_plan(repaired_plan)
    print(f"  Valid: {is_valid}")
    print(f"  Errors: {errors}\n")

    # Show the few-shot example
    print("=" * 70)
    print("FEW-SHOT EXAMPLE (to be added to DSPy predictor):")
    print("=" * 70)
    print()
    print("Desire:", FORK_JOIN_EXAMPLE.desire)
    print("\nCorrect Structure:")
    print("  Nodes:", [n.id for n in FORK_JOIN_EXAMPLE.plan.nodes])
    print("  Edges:", [(e.source, e.target) for e in FORK_JOIN_EXAMPLE.plan.edges])
    print("\nRationale:")
    print(FORK_JOIN_EXAMPLE.rationale)


def test_repair_mechanism():
    """Unit tests for the repair mechanism."""
    print("\n" + "=" * 70)
    print("UNIT TESTS: Graph Repair Mechanism")
    print("=" * 70)
    print()

    # Test 1: Disconnected components
    print("Test 1: Two disconnected components")
    plan1 = BDIPlan(
        goal_description="Test",
        nodes=[
            ActionNode(id="A", action_type="action", params={}, description="Task A"),
            ActionNode(id="B", action_type="action", params={}, description="Task B")
        ],
        edges=[]
    )
    repaired, was_repaired = auto_repair_disconnected_graph(plan1)
    is_valid, _ = verify_plan(repaired)
    assert is_valid, "Repair failed for disconnected components"
    assert was_repaired, "Repair flag not set"
    print("   ✅ PASSED\n")

    # Test 2: Already connected graph
    print("Test 2: Already connected graph (no repair needed)")
    plan2 = BDIPlan(
        goal_description="Test",
        nodes=[
            ActionNode(id="A", action_type="action", params={}, description="Task A"),
            ActionNode(id="B", action_type="action", params={}, description="Task B")
        ],
        edges=[DependencyEdge(source="A", target="B")]
    )
    repaired, was_repaired = auto_repair_disconnected_graph(plan2)
    is_valid, _ = verify_plan(repaired)
    assert is_valid, "Validation failed for already-connected graph"
    assert not was_repaired, "Repair flag incorrectly set for connected graph"
    print("   ✅ PASSED\n")

    # Test 3: Complex multi-component case
    print("Test 3: Three disconnected components")
    plan3 = BDIPlan(
        goal_description="Test",
        nodes=[
            ActionNode(id="A", action_type="action", params={}, description="Task A"),
            ActionNode(id="B", action_type="action", params={}, description="Task B"),
            ActionNode(id="C", action_type="action", params={}, description="Task C"),
        ],
        edges=[
            DependencyEdge(source="A", target="B"),
            # C is isolated
        ]
    )
    repaired, was_repaired = auto_repair_disconnected_graph(plan3)
    is_valid, _ = verify_plan(repaired)
    assert is_valid, "Repair failed for multi-component graph"
    assert was_repaired, "Repair flag not set for multi-component"
    print("   ✅ PASSED\n")

    print("=" * 70)
    print("ALL TESTS PASSED ✅")
    print("=" * 70)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Quick fix for parallel task problem")
    parser.add_argument("--demo", action="store_true", help="Run interactive demo")
    parser.add_argument("--test", action="store_true", help="Run unit tests")

    args = parser.parse_args()

    if args.demo:
        demo_parallel_task_fix()
    elif args.test:
        test_repair_mechanism()
    else:
        print("Usage: python quick_fix_parallel_tasks.py [--demo | --test]")
        print("\nOptions:")
        print("  --demo    Show interactive demo of the repair mechanism")
        print("  --test    Run unit tests for graph repair")
