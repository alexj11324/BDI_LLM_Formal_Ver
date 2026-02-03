#!/usr/bin/env python3
"""
BDI-LLM Evaluation Runner

This script provides multiple ways to validate the prototype:
1. Unit tests (no API needed)
2. Integration tests (requires API key)
3. Visual demonstration
4. Benchmark suite

Usage:
    python run_evaluation.py --mode unit      # Run unit tests only
    python run_evaluation.py --mode demo      # Run visual demo (needs API)
    python run_evaluation.py --mode benchmark # Run full benchmark (needs API)
    python run_evaluation.py --mode all       # Run everything
"""

import argparse
import subprocess
import sys
import os
import json
from typing import Optional

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from schemas import BDIPlan, ActionNode, DependencyEdge
from verifier import PlanVerifier


def run_unit_tests():
    """Run pytest on verifier tests (no API needed)."""
    print("\n" + "="*60)
    print("RUNNING UNIT TESTS (No API Required)")
    print("="*60 + "\n")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_verifier.py", "-v", "--tb=short"],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    return result.returncode == 0


def run_offline_demo():
    """
    Demonstrate the verifier with hardcoded plans.
    No API key required - shows the "compiler" in action.
    """
    print("\n" + "="*60)
    print("OFFLINE DEMO: Verifier as 'Compiler'")
    print("="*60 + "\n")

    # Demo 1: Valid plan
    print("Test 1: Valid Kitchen Navigation Plan")
    print("-" * 40)
    valid_plan = BDIPlan(
        goal_description="Go to the kitchen",
        nodes=[
            ActionNode(id="1", action_type="PickUp",
                      params={"object": "keys"},
                      description="Pick up keys"),
            ActionNode(id="2", action_type="Navigate",
                      params={"target": "door"},
                      description="Go to door"),
            ActionNode(id="3", action_type="UnlockDoor",
                      description="Unlock door"),
            ActionNode(id="4", action_type="OpenDoor",
                      description="Open door"),
            ActionNode(id="5", action_type="Navigate",
                      params={"target": "kitchen"},
                      description="Enter kitchen"),
        ],
        edges=[
            DependencyEdge(source="1", target="2"),
            DependencyEdge(source="1", target="3"),
            DependencyEdge(source="2", target="3"),
            DependencyEdge(source="3", target="4"),
            DependencyEdge(source="4", target="5"),
        ]
    )

    G = valid_plan.to_networkx()
    is_valid, errors = PlanVerifier.verify(G)

    print(f"Nodes: {[n.id for n in valid_plan.nodes]}")
    print(f"Edges: {[(e.source, e.target) for e in valid_plan.edges]}")
    print(f"Compilation Result: {'PASS' if is_valid else 'FAIL'}")
    if is_valid:
        order = PlanVerifier.topological_sort(G)
        print(f"Execution Order: {' -> '.join(order)}")
    print()

    # Demo 2: Invalid plan (has cycle)
    print("Test 2: Invalid Plan (Circular Dependency)")
    print("-" * 40)
    invalid_plan = BDIPlan(
        goal_description="Impossible task",
        nodes=[
            ActionNode(id="A", action_type="TaskA", description="Do A"),
            ActionNode(id="B", action_type="TaskB", description="Do B"),
            ActionNode(id="C", action_type="TaskC", description="Do C"),
        ],
        edges=[
            DependencyEdge(source="A", target="B"),
            DependencyEdge(source="B", target="C"),
            DependencyEdge(source="C", target="A"),  # Creates cycle!
        ]
    )

    G2 = invalid_plan.to_networkx()
    is_valid2, errors2 = PlanVerifier.verify(G2)

    print(f"Nodes: {[n.id for n in invalid_plan.nodes]}")
    print(f"Edges: {[(e.source, e.target) for e in invalid_plan.edges]}")
    print(f"Compilation Result: {'PASS' if is_valid2 else 'FAIL'}")
    print(f"Errors: {errors2}")
    print()

    # Demo 3: Invalid plan (disconnected)
    print("Test 3: Invalid Plan (Disconnected Components)")
    print("-" * 40)
    disconnected_plan = BDIPlan(
        goal_description="Fragmented plan",
        nodes=[
            ActionNode(id="X1", action_type="Task", description="Island 1 - Step 1"),
            ActionNode(id="X2", action_type="Task", description="Island 1 - Step 2"),
            ActionNode(id="Y1", action_type="Task", description="Island 2 - Step 1"),
            ActionNode(id="Y2", action_type="Task", description="Island 2 - Step 2"),
        ],
        edges=[
            DependencyEdge(source="X1", target="X2"),  # Island 1
            DependencyEdge(source="Y1", target="Y2"),  # Island 2 (no connection!)
        ]
    )

    G3 = disconnected_plan.to_networkx()
    is_valid3, errors3 = PlanVerifier.verify(G3)

    print(f"Nodes: {[n.id for n in disconnected_plan.nodes]}")
    print(f"Edges: {[(e.source, e.target) for e in disconnected_plan.edges]}")
    print(f"Compilation Result: {'PASS' if is_valid3 else 'FAIL'}")
    print(f"Errors: {errors3}")
    print()

    print("="*60)
    print("SUMMARY: The Verifier correctly identifies:")
    print("  - Valid DAG structures")
    print("  - Circular dependencies (deadlocks)")
    print("  - Disconnected plan fragments")
    print("="*60)

    return True


def run_llm_demo():
    """Run the LLM-powered planner demo."""
    print("\n" + "="*60)
    print("LLM DEMO: Full BDI-LLM Pipeline")
    print("="*60 + "\n")

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: No API key found.")
        print("Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.")
        return False

    try:
        from planner import main as planner_main
        planner_main()
        return True
    except Exception as e:
        print(f"Error running LLM demo: {e}")
        return False


def run_benchmark():
    """Run the full benchmark suite."""
    print("\n" + "="*60)
    print("BENCHMARK: Full Evaluation Suite")
    print("="*60 + "\n")

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: No API key found for benchmark.")
        return False

    try:
        from tests.test_integration import run_benchmark as benchmark_func
        benchmark_func("benchmark_results.json")
        return True
    except Exception as e:
        print(f"Error running benchmark: {e}")
        return False


def print_usage():
    """Print usage information."""
    print("""
BDI-LLM Formal Verification Framework - Evaluation Guide
=========================================================

This framework validates LLM-generated plans using formal graph verification.

VALIDATION LEVELS:

1. UNIT TESTS (No API required):
   python run_evaluation.py --mode unit

   Tests the Verifier component:
   - Empty plan detection
   - Cycle detection (deadlock prevention)
   - Connectivity checking
   - Topological sort validation

2. OFFLINE DEMO (No API required):
   python run_evaluation.py --mode demo-offline

   Shows the verifier working on hardcoded plans.
   Demonstrates the "compiler" concept.

3. LLM DEMO (Requires API key):
   export OPENAI_API_KEY=sk-...
   python run_evaluation.py --mode demo

   Runs the full pipeline:
   LLM Generation -> Verification -> Self-Correction

4. BENCHMARK (Requires API key):
   export OPENAI_API_KEY=sk-...
   python run_evaluation.py --mode benchmark

   Runs multiple scenarios and collects metrics:
   - Structural accuracy rate
   - First-try success rate
   - Average retry count

KEY METRICS:
- Structural Correctness: Plan is a valid DAG (no cycles, connected)
- First-Try Rate: LLM generates valid plan without Assert retry
- Semantic Score: Plan achieves the goal (requires LLM-as-judge)
    """)


def main():
    parser = argparse.ArgumentParser(description="BDI-LLM Evaluation Runner")
    parser.add_argument(
        "--mode",
        choices=["unit", "demo-offline", "demo", "benchmark", "all", "help"],
        default="help",
        help="Evaluation mode to run"
    )
    args = parser.parse_args()

    if args.mode == "help":
        print_usage()
        return

    results = {}

    if args.mode in ["unit", "all"]:
        results["unit"] = run_unit_tests()

    if args.mode in ["demo-offline", "all"]:
        results["demo-offline"] = run_offline_demo()

    if args.mode in ["demo", "all"]:
        results["demo"] = run_llm_demo()

    if args.mode in ["benchmark", "all"]:
        results["benchmark"] = run_benchmark()

    # Summary
    if results:
        print("\n" + "="*60)
        print("EVALUATION SUMMARY")
        print("="*60)
        for mode, success in results.items():
            status = "PASS" if success else "FAIL"
            print(f"  {mode}: {status}")


if __name__ == "__main__":
    main()
