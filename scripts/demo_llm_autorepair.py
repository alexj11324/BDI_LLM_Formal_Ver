#!/usr/bin/env python3
"""
Live Demo: LLM + Auto-Repair for Parallel Tasks
================================================

This script demonstrates:
1. What LLM actually generates for parallel tasks (spoiler: often wrong)
2. How auto-repair fixes it automatically

Usage:
    export OPENAI_API_KEY=your-key
    python demo_llm_autorepair.py
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.bdi_llm.planner import BDIPlanner
from src.bdi_llm.verifier import PlanVerifier
from scripts.quick_fix_parallel_tasks import auto_repair_disconnected_graph
import json


def print_section(title):
    """Pretty print section headers"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def visualize_plan(plan, label="PLAN"):
    """Print plan structure in readable format"""
    print(f"{label}:")
    print(f"  Goal: {plan.goal_description}")
    print(f"  Nodes ({len(plan.nodes)}):")
    for node in plan.nodes:
        print(f"    - {node.id}: {node.description}")
    print(f"  Edges ({len(plan.edges)}):")
    if plan.edges:
        for edge in plan.edges:
            print(f"    - {edge.source} → {edge.target}")
    else:
        print("    (no edges - DISCONNECTED!)")
    print()


def test_llm_with_parallel_task():
    """Run live LLM test on the classic parallel task failure case"""

    print_section("🤖 LLM PARALLEL TASK TEST")

    # The classic failure case
    beliefs = """
    - Printer is available with paper loaded
    - Email server is accessible
    - Document 'report.pdf' is ready
    """

    desire = "Print the document and send it via email simultaneously"

    print(f"📋 INPUT:")
    print(f"   Beliefs: {beliefs.strip()}")
    print(f"   Desire: {desire}\n")

    print("⏳ Calling LLM (Claude Opus 4 via CMU AI Gateway)...\n")

    # Generate plan with LLM (directly use predictor to avoid DSPy 3.x Assert issues)
    planner = BDIPlanner()

    try:
        # Call the predictor directly
        result = planner.generate_plan(beliefs=beliefs, desire=desire)
        original_plan = result.plan

        print_section("📊 LLM OUTPUT (Original Plan)")
        visualize_plan(original_plan, "GENERATED PLAN")

        # Check if it's valid
        G = original_plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        print(f"🔍 VERIFICATION RESULT:")
        print(f"   Valid: {is_valid}")
        if not is_valid:
            print(f"   ❌ Errors:")
            for error in errors:
                print(f"      - {error}")
        else:
            print(f"   ✅ Plan passed all checks!")

        # If invalid and disconnected, show the repair
        if not is_valid and "disconnected" in str(errors).lower():
            print_section("🔧 AUTO-REPAIR IN ACTION")

            print("Applying auto_repair_disconnected_graph()...\n")
            repaired_plan, was_repaired = auto_repair_disconnected_graph(original_plan)

            if was_repaired:
                visualize_plan(repaired_plan, "REPAIRED PLAN")

                # Re-verify
                G_repaired = repaired_plan.to_networkx()
                is_valid_repaired, errors_repaired = PlanVerifier.verify(G_repaired)

                print(f"🔍 RE-VERIFICATION RESULT:")
                print(f"   Valid: {is_valid_repaired}")
                if is_valid_repaired:
                    print(f"   ✅ Repaired plan passed all checks!")
                else:
                    print(f"   ❌ Still has errors: {errors_repaired}")

                print_section("📈 COMPARISON")
                print(f"{'Metric':<30} {'Original':<15} {'Repaired':<15}")
                print("-" * 60)
                print(f"{'Number of nodes':<30} {len(original_plan.nodes):<15} {len(repaired_plan.nodes):<15}")
                print(f"{'Number of edges':<30} {len(original_plan.edges):<15} {len(repaired_plan.edges):<15}")
                print(f"{'Weakly connected':<30} {str(not 'disconnected' in str(errors).lower()):<15} {str(is_valid_repaired):<15}")
                print(f"{'Is DAG':<30} {str(is_valid):<15} {str(is_valid_repaired):<15}")

        print_section("✅ DEMO COMPLETE")
        print("Summary:")
        print(f"  • LLM generated {'valid' if is_valid else 'INVALID'} plan on first try")
        if not is_valid and was_repaired:
            print(f"  • Auto-repair successfully fixed the disconnection issue")
            print(f"  • Final result: {'✅ VALID' if is_valid_repaired else '❌ STILL INVALID'}")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\nTroubleshooting:")
        print("  1. Check OPENAI_API_KEY is set:")
        print("     export OPENAI_API_KEY=your-key")
        print("  2. Verify CMU AI Gateway access")
        print("  3. Check network connectivity")
        return


def test_sequential_task():
    """Test LLM on a sequential task (should work fine)"""

    print_section("🤖 LLM SEQUENTIAL TASK TEST (Control)")

    beliefs = """
    - Door is currently closed
    - Room contains a table
    - Key is in my pocket
    """

    desire = "Enter the room and sit at the table"

    print(f"📋 INPUT:")
    print(f"   Beliefs: {beliefs.strip()}")
    print(f"   Desire: {desire}\n")

    print("⏳ Calling LLM...\n")

    planner = BDIPlanner()

    try:
        result = planner.generate_plan(beliefs=beliefs, desire=desire)
        plan = result.plan

        visualize_plan(plan, "GENERATED PLAN")

        G = plan.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)

        print(f"🔍 VERIFICATION:")
        print(f"   Valid: {is_valid}")
        if is_valid:
            print(f"   ✅ Sequential tasks work well!")
        else:
            print(f"   ❌ Errors: {errors}")

    except Exception as e:
        print(f"❌ ERROR: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Live LLM + Auto-Repair Demo")
    parser.add_argument("--mode", choices=["parallel", "sequential", "both"],
                       default="parallel",
                       help="Which test to run")

    args = parser.parse_args()

    # Check API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("❌ ERROR: OPENAI_API_KEY environment variable not set")
        print("\nPlease set it first:")
        print("  export OPENAI_API_KEY=your-api-key")
        print("\nFor CMU students, get your key from:")
        print("  https://ai-gateway.andrew.cmu.edu/")
        sys.exit(1)

    print("🚀 Starting Live LLM Demo...")
    print(f"   Model: Claude Opus 4 (via CMU AI Gateway)")
    print(f"   Mode: {args.mode}")

    if args.mode in ["parallel", "both"]:
        test_llm_with_parallel_task()

    if args.mode in ["sequential", "both"]:
        test_sequential_task()
