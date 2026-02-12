#!/usr/bin/env python3
"""
PlanBench Comparison: BDI vs Non-BDI
=====================================

Compares planning success rates between:
1. BDI-LLM (with formal verifier + auto-repair)
2. Vanilla LLM (direct planning without verification)

Usage:
    export OPENAI_API_KEY=your-key
    python run_planbench_comparison.py --n_samples 50 --mode both

Author: BDI-LLM Research
Date: 2026-02-03
"""

import sys
import os
import json
from pathlib import Path
from typing import List, Dict, Tuple
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.bdi_llm.planner import BDIPlanner
from src.bdi_llm.schemas import BDIPlan, ActionNode, DependencyEdge
from src.bdi_llm.verifier import PlanVerifier
from scripts.quick_fix_parallel_tasks import auto_repair_disconnected_graph
import networkx as nx
import dspy


# ============================================================================
# TEST SCENARIOS (Diverse Planning Tasks)
# ============================================================================

TEST_SCENARIOS = [
    # Sequential tasks (LLM should handle well)
    {
        "id": "seq_001",
        "type": "sequential",
        "beliefs": "Door is locked. Key is on table. Room has a chair.",
        "desire": "Enter the room and sit on the chair",
        "expected_structure": "linear_chain"
    },
    {
        "id": "seq_002",
        "type": "sequential",
        "beliefs": "Car needs fuel. Gas station is 2 blocks away. Wallet has cash.",
        "desire": "Fill up the car with gas",
        "expected_structure": "linear_chain"
    },
    {
        "id": "seq_003",
        "type": "sequential",
        "beliefs": "Laptop is off. Presentation file is on desktop. Projector is available.",
        "desire": "Start the presentation",
        "expected_structure": "linear_chain"
    },

    # Parallel tasks (LLM often fails without BDI)
    {
        "id": "par_001",
        "type": "parallel",
        "beliefs": "Printer is ready. Email server is online. Document is saved.",
        "desire": "Print the document and send it via email simultaneously",
        "expected_structure": "fork_join"
    },
    {
        "id": "par_002",
        "type": "parallel",
        "beliefs": "Database is accessible. Cache server is running. API is ready.",
        "desire": "Fetch data from database and update cache at the same time",
        "expected_structure": "fork_join"
    },
    {
        "id": "par_003",
        "type": "parallel",
        "beliefs": "Backup server is online. Log collector is active. Monitoring is enabled.",
        "desire": "Create backup and collect logs concurrently",
        "expected_structure": "fork_join"
    },

    # Mixed (sequential + parallel)
    {
        "id": "mix_001",
        "type": "mixed",
        "beliefs": "User is logged out. System has cache. Database contains user data.",
        "desire": "Login, then fetch profile and load preferences in parallel",
        "expected_structure": "sequential_then_parallel"
    },
    {
        "id": "mix_002",
        "type": "mixed",
        "beliefs": "File is encrypted. Decryption key is available. Two recipients need the file.",
        "desire": "Decrypt the file, then send to both recipients simultaneously",
        "expected_structure": "sequential_then_parallel"
    },

    # Complex tasks (multi-step with dependencies)
    {
        "id": "complex_001",
        "type": "complex",
        "beliefs": "Project has 3 modules (A, B, C). Module B depends on A. Module C depends on B. Tests must run after all modules compile.",
        "desire": "Build the entire project and run tests",
        "expected_structure": "dependency_chain"
    },
    {
        "id": "complex_002",
        "type": "complex",
        "beliefs": "Order needs payment, packaging, and shipping. Payment must happen first. Packaging and label printing can happen in parallel after payment. Shipping happens last.",
        "desire": "Fulfill the customer order",
        "expected_structure": "complex_dag"
    }
]


# ============================================================================
# VANILLA LLM PLANNER (No BDI, No Verification)
# ============================================================================

class VanillaLLMPlanner:
    """Direct LLM planning without BDI framework"""

    def __init__(self):
        # Uses same LLM as BDI but without verification/repair
        self.predictor = dspy.Predict(
            "beliefs, desire -> plan_description: str"
        )

    def plan(self, beliefs: str, desire: str) -> Tuple[str, bool]:
        """
        Generate plan using vanilla LLM (no structured output, no verification)

        Returns:
            (plan_description, is_valid_placeholder)
        """
        try:
            result = self.predictor(
                beliefs=beliefs,
                desire=f"Generate a step-by-step plan to achieve: {desire}"
            )
            plan_text = result.plan_description

            # Vanilla LLM has no way to verify validity
            # We return True as placeholder (actual validity unknown)
            return plan_text, True

        except Exception as e:
            return f"ERROR: {str(e)}", False


# ============================================================================
# BDI PLANNER WITH AUTO-REPAIR
# ============================================================================

class BDIPlannerWithRepair:
    """BDI Planner with auto-repair for disconnected graphs"""

    def __init__(self):
        self.planner = BDIPlanner()

    def plan(self, beliefs: str, desire: str) -> Tuple[BDIPlan, bool, Dict]:
        """
        Generate plan using BDI framework + auto-repair

        Returns:
            (plan, is_valid, metrics)
        """
        metrics = {
            "auto_repaired": False,
            "verification_errors": [],
            "num_retries": 0
        }

        try:
            # Generate plan with LLM
            result = self.planner.generate_plan(beliefs=beliefs, desire=desire)
            plan = result.plan

            # Verify
            G = plan.to_networkx()
            is_valid, errors = PlanVerifier.verify(G)

            metrics["verification_errors"] = errors

            # If disconnected, apply auto-repair
            if not is_valid and any("disconnected" in str(e).lower() for e in errors):
                plan, was_repaired = auto_repair_disconnected_graph(plan)
                metrics["auto_repaired"] = was_repaired

                if was_repaired:
                    # Re-verify
                    G = plan.to_networkx()
                    is_valid, errors = PlanVerifier.verify(G)
                    metrics["verification_errors"] = errors

            return plan, is_valid, metrics

        except Exception as e:
            metrics["verification_errors"] = [str(e)]
            # Return minimal plan
            plan = BDIPlan(
                goal_description=desire,
                nodes=[],
                edges=[]
            )
            return plan, False, metrics


# ============================================================================
# EVALUATION FUNCTIONS
# ============================================================================

def evaluate_plan_quality(plan: BDIPlan, scenario: Dict) -> Dict:
    """
    Evaluate plan quality beyond just validity

    Returns:
        Quality metrics
    """
    G = plan.to_networkx()

    metrics = {
        "num_nodes": len(plan.nodes),
        "num_edges": len(plan.edges),
        "is_dag": nx.is_directed_acyclic_graph(G) if len(G.nodes) > 0 else False,
        "is_connected": nx.is_weakly_connected(G) if len(G.nodes) > 0 else False,
        "avg_degree": sum(dict(G.degree()).values()) / len(G.nodes) if len(G.nodes) > 0 else 0,
    }

    # Check if structure matches expected
    expected = scenario["expected_structure"]
    if expected == "linear_chain":
        metrics["structure_match"] = metrics["num_edges"] == metrics["num_nodes"] - 1
    elif expected == "fork_join":
        # Should have START/END nodes with branches
        metrics["structure_match"] = any(node.id == "START" for node in plan.nodes) and \
                                     any(node.id == "END" for node in plan.nodes)
    else:
        metrics["structure_match"] = True  # Don't check complex structures

    return metrics


def run_comparison(scenarios: List[Dict], n_samples: int = None) -> Dict:
    """
    Run full comparison between BDI and Vanilla LLM

    Args:
        scenarios: List of test scenarios
        n_samples: Number of scenarios to test (None = all)

    Returns:
        Results dictionary
    """
    if n_samples:
        scenarios = scenarios[:n_samples]

    print(f"\n{'='*80}")
    print(f"  PLANBENCH COMPARISON: BDI vs Vanilla LLM")
    print(f"{'='*80}\n")
    print(f"Testing {len(scenarios)} scenarios...")
    print(f"Model: Claude Opus 4 (CMU AI Gateway)\n")

    bdi_planner = BDIPlannerWithRepair()
    vanilla_planner = VanillaLLMPlanner()

    results = {
        "timestamp": datetime.now().isoformat(),
        "n_scenarios": len(scenarios),
        "bdi_results": [],
        "vanilla_results": [],
        "summary": {}
    }

    for i, scenario in enumerate(scenarios):
        print(f"\n[{i+1}/{len(scenarios)}] Testing: {scenario['id']} ({scenario['type']})")
        print(f"  Desire: {scenario['desire']}")

        # ---- BDI Test ----
        print("  🔷 BDI-LLM: ", end="", flush=True)
        start_time = time.time()

        try:
            bdi_plan, bdi_valid, bdi_metrics = bdi_planner.plan(
                scenario["beliefs"],
                scenario["desire"]
            )
            bdi_time = time.time() - start_time

            quality = evaluate_plan_quality(bdi_plan, scenario)

            bdi_result = {
                "scenario_id": scenario["id"],
                "is_valid": bdi_valid,
                "time_seconds": bdi_time,
                "metrics": bdi_metrics,
                "quality": quality
            }
            results["bdi_results"].append(bdi_result)

            status = "✅ VALID" if bdi_valid else "❌ INVALID"
            repair_note = " (auto-repaired)" if bdi_metrics.get("auto_repaired") else ""
            print(f"{status}{repair_note} ({bdi_time:.2f}s)")

        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            results["bdi_results"].append({
                "scenario_id": scenario["id"],
                "is_valid": False,
                "error": str(e)
            })

        # ---- Vanilla LLM Test ----
        print("  🔶 Vanilla LLM: ", end="", flush=True)
        start_time = time.time()

        try:
            vanilla_plan_text, vanilla_completed = vanilla_planner.plan(
                scenario["beliefs"],
                scenario["desire"]
            )
            vanilla_time = time.time() - start_time

            vanilla_result = {
                "scenario_id": scenario["id"],
                "completed": vanilla_completed,
                "time_seconds": vanilla_time,
                "plan_length": len(vanilla_plan_text.split('\n'))
            }
            results["vanilla_results"].append(vanilla_result)

            status = "✅ GENERATED" if vanilla_completed else "❌ FAILED"
            print(f"{status} ({vanilla_time:.2f}s, {vanilla_result['plan_length']} lines)")

        except Exception as e:
            print(f"❌ ERROR: {str(e)}")
            results["vanilla_results"].append({
                "scenario_id": scenario["id"],
                "completed": False,
                "error": str(e)
            })

    # Compute summary statistics
    compute_summary(results)

    return results


def compute_summary(results: Dict):
    """Compute summary statistics"""

    bdi_results = results["bdi_results"]
    vanilla_results = results["vanilla_results"]

    # BDI statistics
    bdi_valid_count = sum(1 for r in bdi_results if r.get("is_valid", False))
    bdi_repaired_count = sum(1 for r in bdi_results if r.get("metrics", {}).get("auto_repaired", False))
    bdi_avg_time = sum(r.get("time_seconds", 0) for r in bdi_results) / len(bdi_results) if bdi_results else 0

    # Vanilla statistics
    vanilla_completed_count = sum(1 for r in vanilla_results if r.get("completed", False))
    vanilla_avg_time = sum(r.get("time_seconds", 0) for r in vanilla_results) / len(vanilla_results) if vanilla_results else 0

    # By task type
    task_types = {}
    for r in bdi_results:
        scenario_id = r["scenario_id"]
        task_type = scenario_id.split("_")[0]
        if task_type not in task_types:
            task_types[task_type] = {"bdi_valid": 0, "total": 0}
        task_types[task_type]["total"] += 1
        if r.get("is_valid", False):
            task_types[task_type]["bdi_valid"] += 1

    results["summary"] = {
        "bdi": {
            "success_rate": bdi_valid_count / len(bdi_results) if bdi_results else 0,
            "valid_count": bdi_valid_count,
            "repaired_count": bdi_repaired_count,
            "avg_time_seconds": bdi_avg_time
        },
        "vanilla": {
            "completion_rate": vanilla_completed_count / len(vanilla_results) if vanilla_results else 0,
            "completed_count": vanilla_completed_count,
            "avg_time_seconds": vanilla_avg_time
        },
        "by_task_type": task_types
    }


def print_summary(results: Dict):
    """Pretty print summary results"""

    print(f"\n{'='*80}")
    print(f"  FINAL RESULTS")
    print(f"{'='*80}\n")

    summary = results["summary"]

    print(f"{'Method':<20} {'Success Rate':<20} {'Valid/Total':<20} {'Avg Time (s)':<15}")
    print("-" * 75)

    # BDI Results
    bdi = summary["bdi"]
    print(f"{'BDI-LLM':<20} {bdi['success_rate']*100:>6.1f}% {'':<12} "
          f"{bdi['valid_count']}/{results['n_scenarios']:<15} {bdi['avg_time_seconds']:>10.2f}")

    # Vanilla Results (note: we can't verify validity without BDI framework)
    vanilla = summary["vanilla"]
    print(f"{'Vanilla LLM':<20} {'N/A (unverified)':<20} "
          f"{vanilla['completed_count']}/{results['n_scenarios']:<15} {vanilla['avg_time_seconds']:>10.2f}")

    print()
    print(f"Note: Vanilla LLM generates unstructured text plans (no formal verification)")
    print(f"      BDI-LLM generates formally verified DAG structures")
    print()

    # Task type breakdown
    print(f"\n{'Task Type':<15} {'BDI Success Rate':<20} {'Count':<10}")
    print("-" * 45)
    for task_type, stats in summary["by_task_type"].items():
        rate = stats["bdi_valid"] / stats["total"] if stats["total"] > 0 else 0
        print(f"{task_type:<15} {rate*100:>6.1f}% {'':<12} {stats['bdi_valid']}/{stats['total']}")

    # Auto-repair statistics
    print(f"\n{'Auto-Repair Statistics':<30}")
    print("-" * 40)
    print(f"  Repairs triggered: {bdi['repaired_count']}")
    print(f"  Repair success rate: {bdi['repaired_count']/results['n_scenarios']*100:.1f}%")


def save_results(results: Dict, output_file: str = "planbench_comparison_results.json"):
    """Save results to JSON file"""
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n✅ Results saved to {output_file}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="PlanBench Comparison: BDI vs Vanilla LLM")
    parser.add_argument("--n_samples", type=int, default=None,
                       help="Number of scenarios to test (default: all)")
    parser.add_argument("--mode", choices=["bdi", "vanilla", "both"], default="both",
                       help="Which planner to test")
    parser.add_argument("--output", type=str, default="planbench_comparison_results.json",
                       help="Output file for results")

    args = parser.parse_args()

    # Check API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("❌ ERROR: OPENAI_API_KEY not set")
        print("  export OPENAI_API_KEY=your-key")
        sys.exit(1)

    # Run comparison
    results = run_comparison(TEST_SCENARIOS, args.n_samples)

    # Print summary
    print_summary(results)

    # Save results
    save_results(results, args.output)

    print(f"\n{'='*80}")
    print(f"  COMPARISON COMPLETE")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
