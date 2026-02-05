#!/usr/bin/env python3
"""
Stress Test: Force Parallel Task Failures
==========================================

Specifically designed to trigger the disconnected graph problem
by using explicit "simultaneously" and "in parallel" keywords.

This test will show the TRUE value of auto-repair.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.bdi_llm.planner import BDIPlanner
from src.bdi_llm.verifier import PlanVerifier
from scripts.quick_fix_parallel_tasks import auto_repair_disconnected_graph
import time


STRESS_TEST_SCENARIOS = [
    {
        "id": "stress_par_001",
        "beliefs": "Printer ready. Email server online. Document saved.",
        "desire": "Print document and email it simultaneously"
    },
    {
        "id": "stress_par_002",
        "beliefs": "Database accessible. Cache running. Network stable.",
        "desire": "Query database and update cache at exactly the same time"
    },
    {
        "id": "stress_par_003",
        "beliefs": "Backup server ready. Log collector active.",
        "desire": "Create backup in parallel with log collection"
    },
    {
        "id": "stress_par_004",
        "beliefs": "Two APIs available: API_A and API_B. Both are independent.",
        "desire": "Call API_A and API_B concurrently without waiting"
    },
    {
        "id": "stress_par_005",
        "beliefs": "File compression tool ready. Encryption tool available.",
        "desire": "Compress and encrypt file simultaneously in separate processes"
    },
]


def test_without_repair(scenario):
    """Test BDI planner WITHOUT auto-repair"""
    planner = BDIPlanner()

    result = planner.generate_plan(
        beliefs=scenario["beliefs"],
        desire=scenario["desire"]
    )
    plan = result.plan

    # Verify
    G = plan.to_networkx()
    is_valid, errors = PlanVerifier.verify(G)

    return {
        "scenario_id": scenario["id"],
        "is_valid": is_valid,
        "errors": errors,
        "num_nodes": len(plan.nodes),
        "num_edges": len(plan.edges)
    }


def test_with_repair(scenario):
    """Test BDI planner WITH auto-repair"""
    planner = BDIPlanner()

    result = planner.generate_plan(
        beliefs=scenario["beliefs"],
        desire=scenario["desire"]
    )
    plan = result.plan

    # Verify
    G = plan.to_networkx()
    is_valid_before, errors_before = PlanVerifier.verify(G)

    # Apply auto-repair if needed
    repaired = False
    if not is_valid_before and any("disconnected" in str(e).lower() for e in errors_before):
        plan, repaired = auto_repair_disconnected_graph(plan)

        # Re-verify
        G = plan.to_networkx()
        is_valid_after, errors_after = PlanVerifier.verify(G)
    else:
        is_valid_after = is_valid_before
        errors_after = errors_before

    return {
        "scenario_id": scenario["id"],
        "is_valid_before": is_valid_before,
        "is_valid_after": is_valid_after,
        "was_repaired": repaired,
        "errors_before": errors_before,
        "errors_after": errors_after,
        "num_nodes_before": len([n for n in plan.nodes if n.id not in ["START", "END"]]),
        "num_nodes_after": len(plan.nodes)
    }


def main():
    print("\n" + "="*80)
    print("  STRESS TEST: Parallel Task Failures")
    print("="*80 + "\n")
    print(f"Testing {len(STRESS_TEST_SCENARIOS)} scenarios designed to trigger failures\n")

    # Check API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("❌ API key not set")
        sys.exit(1)

    results_without_repair = []
    results_with_repair = []

    print("=" * 80)
    print("  PHASE 1: WITHOUT Auto-Repair")
    print("=" * 80 + "\n")

    for i, scenario in enumerate(STRESS_TEST_SCENARIOS):
        print(f"[{i+1}/{len(STRESS_TEST_SCENARIOS)}] {scenario['id']}")
        print(f"  Desire: {scenario['desire']}")

        try:
            result = test_without_repair(scenario)
            results_without_repair.append(result)

            status = "✅ VALID" if result["is_valid"] else "❌ INVALID"
            print(f"  Result: {status}")
            if not result["is_valid"]:
                print(f"  Errors: {result['errors']}")
            print(f"  Graph: {result['num_nodes']} nodes, {result['num_edges']} edges\n")

        except Exception as e:
            print(f"  ❌ ERROR: {e}\n")
            results_without_repair.append({
                "scenario_id": scenario["id"],
                "is_valid": False,
                "error": str(e)
            })

    print("\n" + "=" * 80)
    print("  PHASE 2: WITH Auto-Repair")
    print("=" * 80 + "\n")

    for i, scenario in enumerate(STRESS_TEST_SCENARIOS):
        print(f"[{i+1}/{len(STRESS_TEST_SCENARIOS)}] {scenario['id']}")
        print(f"  Desire: {scenario['desire']}")

        try:
            result = test_with_repair(scenario)
            results_with_repair.append(result)

            before_status = "✅" if result["is_valid_before"] else "❌"
            after_status = "✅" if result["is_valid_after"] else "❌"
            repair_note = " (🔧 REPAIRED)" if result["was_repaired"] else ""

            print(f"  Before: {before_status} | After: {after_status}{repair_note}")

            if result["was_repaired"]:
                print(f"  Nodes: {result['num_nodes_before']} → {result['num_nodes_after']}")

            print()

        except Exception as e:
            print(f"  ❌ ERROR: {e}\n")

    # Summary
    print("\n" + "=" * 80)
    print("  SUMMARY")
    print("=" * 80 + "\n")

    # Without repair statistics
    valid_without_repair = sum(1 for r in results_without_repair if r.get("is_valid", False))
    failed_without_repair = len(results_without_repair) - valid_without_repair

    # With repair statistics
    valid_before_repair = sum(1 for r in results_with_repair if r.get("is_valid_before", False))
    valid_after_repair = sum(1 for r in results_with_repair if r.get("is_valid_after", False))
    repairs_triggered = sum(1 for r in results_with_repair if r.get("was_repaired", False))

    print(f"{'Metric':<35} {'Without Repair':<20} {'With Repair':<20}")
    print("-" * 75)
    print(f"{'Total tests':<35} {len(results_without_repair):<20} {len(results_with_repair):<20}")
    print(f"{'Valid plans':<35} {valid_without_repair:<20} {valid_after_repair:<20}")
    print(f"{'Failed plans':<35} {failed_without_repair:<20} {len(results_with_repair) - valid_after_repair:<20}")
    print(f"{'Success rate':<35} {valid_without_repair/len(results_without_repair)*100:.1f}%{'':<15} {valid_after_repair/len(results_with_repair)*100:.1f}%")
    print(f"{'Repairs triggered':<35} {'N/A':<20} {repairs_triggered:<20}")
    print()

    if repairs_triggered > 0:
        improvement = valid_after_repair - valid_before_repair
        print(f"✅ Auto-repair fixed {improvement} out of {failed_without_repair} failures!")
        print(f"   Repair success rate: {improvement/repairs_triggered*100:.1f}%\n")
    else:
        print("⚠️  No repairs triggered - LLM performed perfectly on this run\n")

    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
