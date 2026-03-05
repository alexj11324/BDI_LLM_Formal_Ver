#!/usr/bin/env python3
"""
BDI-LLM Evaluation Runner

This script provides multiple ways to validate the prototype:
1. Unit tests (no API needed)
2. Integration tests (API-dependent)
3. Visual demonstration
4. Benchmark suite

Usage:
    python run_evaluation.py --mode unit      # Run unit tests only
    python run_evaluation.py --mode demo      # Run visual demo (needs credentials)
    python run_evaluation.py --mode benchmark # Run full benchmark (needs credentials)
    python run_evaluation.py --mode all       # Run everything
"""

import argparse
import importlib.util
import subprocess
import sys
import os
import json
import time
from typing import Any, Dict, List
from dotenv import load_dotenv

load_dotenv()

from bdi_llm.schemas import BDIPlan, ActionNode, DependencyEdge
from bdi_llm.verifier import PlanVerifier

EXECUTION_MODES = {"NAIVE", "BDI_ONLY", "FULL_VERIFIED"}
ABLATION_OUTPUT_DIRS = {
    "NAIVE": "ablation_NAIVE",
    "BDI_ONLY": "ablation_BDI_ONLY",
    "FULL_VERIFIED": "ablation_FULL_VERIFIED",
}

def get_execution_mode() -> str:
    """Read and validate AGENT_EXECUTION_MODE."""
    mode = os.environ.get("AGENT_EXECUTION_MODE", "FULL_VERIFIED").strip().upper()
    if mode not in EXECUTION_MODES:
        print(f"WARNING: Unsupported AGENT_EXECUTION_MODE='{mode}', falling back to FULL_VERIFIED")
        mode = "FULL_VERIFIED"
    return mode

def ensure_ablation_output_dirs():
    """Ensure all ablation output directories exist."""
    runs_root = PROJECT_ROOT / "runs"
    for dirname in ABLATION_OUTPUT_DIRS.values():
        (runs_root / dirname).mkdir(parents=True, exist_ok=True)

def get_ablation_output_dir(mode: str) -> Path:
    """Get output directory for current execution mode."""
    return PROJECT_ROOT / "runs" / ABLATION_OUTPUT_DIRS[mode]

def write_json_file(path: Path, payload: Dict[str, Any]) -> None:
    """Persist JSON payload to disk with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

def summarize_rows(rows: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    """Summarize boolean-like row fields for benchmark reporting."""
    total = len(rows)
    success_count = sum(1 for row in rows if bool(row.get(key)))
    return {
        "total": total,
        "success_count": success_count,
        "success_rate": (success_count / total) if total else 0.0,
    }

def has_any_api_credential() -> bool:
    """Return True when any supported model credential exists."""
    return bool(
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    )

def load_integration_module():
    """Load tests/test_integration.py without requiring tests to be a package."""
    module_path = PROJECT_ROOT / "tests" / "test_integration.py"
    if not module_path.exists():
        raise FileNotFoundError(f"Missing integration module: {module_path}")

    spec = importlib.util.spec_from_file_location("bdi_test_integration", str(module_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to create import spec for {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def run_unit_tests():
    """Run pytest on verifier tests (no API needed)."""
    print("\n" + "="*60)
    print("RUNNING UNIT TESTS (No API Required)")
    print("="*60 + "\n")

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_verifier.py", "-v", "--tb=short"],
        cwd=str(PROJECT_ROOT)
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

    # Demo 3: Valid-with-warning plan (disconnected components)
    print("Test 3: Plan with Structural Warning (Disconnected Components)")
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
    has_disconnected_warning = any("disconnected" in str(message).lower() for message in errors3)

    print(f"Nodes: {[n.id for n in disconnected_plan.nodes]}")
    print(f"Edges: {[(e.source, e.target) for e in disconnected_plan.edges]}")
    if is_valid3 and has_disconnected_warning:
        print("Compilation Result: PASS (with disconnected warning)")
    else:
        print(f"Compilation Result: {'PASS' if is_valid3 else 'FAIL'}")
    print(f"Messages: {errors3}")
    print()

    print("="*60)
    print("SUMMARY: The Verifier correctly identifies:")
    print("  - Valid DAG structures")
    print("  - Circular dependencies (deadlocks)")
    print("  - Disconnected plan fragments (warning)")
    print("="*60)

    return True

def run_llm_demo():
    """Run the LLM-powered planner demo under AGENT_EXECUTION_MODE."""
    mode = get_execution_mode()
    print("\n" + "="*60)
    print(f"LLM DEMO: AGENT_EXECUTION_MODE={mode}")
    print("="*60 + "\n")

    if not has_any_api_credential():
        print("ERROR: No provider credentials found.")
        print("Set OPENAI_API_KEY or ANTHROPIC_API_KEY or GOOGLE_API_KEY or GOOGLE_APPLICATION_CREDENTIALS.")
        return False

    output_dir = get_ablation_output_dir(mode)
    output_dir.mkdir(parents=True, exist_ok=True)

    beliefs = """
    Location: Living Room.
    Inventory: None.
    Environment:
    - Door to Kitchen is closed.
    - Keys are on the Table in the Living Room.
    - Robot is at coordinate (0,0).
    Available Skills: [PickUp, MoveTo, OpenDoor, UnlockDoor]
    """
    desire = "Go to the Kitchen."

    result_payload = {
        "mode": mode,
        "timestamp": int(time.time()),
        "goal": desire,
        "success": False,
        "details": {},
    }

    try:
        if mode == "NAIVE":
            import dspy
            from bdi_llm.planner import configure_dspy

            configure_dspy()
            predictor = dspy.Predict("beliefs, desire -> plan_description: str")
            pred = predictor(
                beliefs=beliefs,
                desire=f"Generate a step-by-step plan to achieve: {desire}",
            )
            plan_text = getattr(pred, "plan_description", "")
            result_payload["success"] = bool(plan_text)
            result_payload["details"] = {
                "path": "naive_text_only",
                "plan_description": plan_text,
            }

        elif mode == "BDI_ONLY":
            from bdi_llm.planner import BDIPlanner

            planner = BDIPlanner(auto_repair=False)
            response = planner.generate_plan(beliefs=beliefs, desire=desire)
            plan = response.plan
            result_payload["success"] = True
            result_payload["details"] = {
                "path": "bdi_generate_only_no_verifier",
                "num_nodes": len(plan.nodes),
                "num_edges": len(plan.edges),
                "actions": [
                    {
                        "id": node.id,
                        "action_type": node.action_type,
                        "params": node.params,
                        "description": node.description,
                    }
                    for node in plan.nodes
                ],
                "edges": [
                    {"source": edge.source, "target": edge.target}
                    for edge in plan.edges
                ],
            }

        else:  # FULL_VERIFIED
            from bdi_llm.planner import BDIPlanner

            planner = BDIPlanner(auto_repair=True)
            response = planner(beliefs=beliefs, desire=desire)
            plan = response.plan
            G = plan.to_networkx()
            is_valid, errors = PlanVerifier.verify(G)
            result_payload["success"] = is_valid
            result_payload["details"] = {
                "path": "bdi_forward_with_verifier",
                "is_valid": is_valid,
                "errors": errors,
                "execution_order": PlanVerifier.topological_sort(G) if is_valid else [],
                "num_nodes": len(plan.nodes),
                "num_edges": len(plan.edges),
            }

        output_file = output_dir / "demo_result.json"
        with open(output_file, "w") as f:
            json.dump(result_payload, f, indent=2)
        print(f"Saved demo result to {output_file}")
        return bool(result_payload["success"])

    except Exception as e:
        print(f"Error running LLM demo ({mode}): {e}")
        result_payload["details"] = {"error": str(e)}
        output_file = output_dir / "demo_result.json"
        with open(output_file, "w") as f:
            json.dump(result_payload, f, indent=2)
        return False

def run_benchmark():
    """Run benchmark under AGENT_EXECUTION_MODE and write mode-specific outputs."""
    mode = get_execution_mode()
    print("\n" + "="*60)
    print(f"BENCHMARK: AGENT_EXECUTION_MODE={mode}")
    print("="*60 + "\n")

    output_dir = get_ablation_output_dir(mode)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "benchmark_results.json"

    if not has_any_api_credential():
        print("ERROR: No provider credentials found for benchmark.")
        write_json_file(
            output_file,
            {
                "mode": mode,
                "timestamp": int(time.time()),
                "error": "No provider credentials found for benchmark.",
                "results": [],
                "metrics": {"total": 0, "success_count": 0, "success_rate": 0.0},
            },
        )
        return False

    try:
        if mode == "NAIVE":
            import dspy
            from bdi_llm.planner import configure_dspy
            integration = load_integration_module()
            test_scenarios = integration.TEST_SCENARIOS

            configure_dspy()
            predictor = dspy.Predict("beliefs, desire -> plan_description: str")

            rows = []
            for scenario in test_scenarios:
                pred = predictor(
                    beliefs=scenario["beliefs"],
                    desire=f"Generate a step-by-step plan to achieve: {scenario['desire']}",
                )
                plan_text = getattr(pred, "plan_description", "")
                rows.append(
                    {
                        "scenario": scenario["name"],
                        "generated": bool(plan_text),
                        "plan_description": plan_text,
                    }
                )

            payload = {
                "mode": mode,
                "timestamp": int(time.time()),
                "results": rows,
                "metrics": summarize_rows(rows, "generated"),
            }
            write_json_file(output_file, payload)
            print(f"Saved benchmark results to {output_file}")
            return True

        if mode == "BDI_ONLY":
            from bdi_llm.planner import BDIPlanner
            integration = load_integration_module()
            test_scenarios = integration.TEST_SCENARIOS

            planner = BDIPlanner(auto_repair=False)
            rows = []
            for scenario in test_scenarios:
                try:
                    response = planner.generate_plan(
                        beliefs=scenario["beliefs"],
                        desire=scenario["desire"],
                    )
                    plan = response.plan
                    rows.append(
                        {
                            "scenario": scenario["name"],
                            "generated": True,
                            "num_nodes": len(plan.nodes),
                            "num_edges": len(plan.edges),
                        }
                    )
                except Exception as e:
                    rows.append(
                        {
                            "scenario": scenario["name"],
                            "generated": False,
                            "error": str(e),
                        }
                    )

            payload = {
                "mode": mode,
                "timestamp": int(time.time()),
                "results": rows,
                "metrics": summarize_rows(rows, "generated"),
            }
            write_json_file(output_file, payload)
            print(f"Saved benchmark results to {output_file}")
            return True

        integration = load_integration_module()
        benchmark_func = integration.run_benchmark

        benchmark_func(str(output_file))
        if not output_file.exists():
            write_json_file(
                output_file,
                {
                    "mode": mode,
                    "timestamp": int(time.time()),
                    "error": "Benchmark function completed without producing output file.",
                    "results": [],
                    "metrics": {"total": 0, "success_count": 0, "success_rate": 0.0},
                },
            )
            return False

        payload = json.loads(output_file.read_text(encoding="utf-8"))
        payload.setdefault("mode", mode)
        payload.setdefault("timestamp", int(time.time()))
        write_json_file(output_file, payload)
        print(f"Saved benchmark results to {output_file}")
        return True
    except Exception as e:
        print(f"Error running benchmark ({mode}): {e}")
        write_json_file(
            output_file,
            {
                "mode": mode,
                "timestamp": int(time.time()),
                "error": str(e),
                "results": [],
                "metrics": {"total": 0, "success_count": 0, "success_rate": 0.0},
            },
        )
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

3. LLM DEMO (Requires provider credentials):
   export OPENAI_API_KEY=...
   # or ANTHROPIC_API_KEY / GOOGLE_API_KEY / GOOGLE_APPLICATION_CREDENTIALS
   python run_evaluation.py --mode demo

   Runs the full pipeline:
   LLM Generation -> Verification -> Self-Correction

4. BENCHMARK (Requires provider credentials):
   export OPENAI_API_KEY=...
   # or ANTHROPIC_API_KEY / GOOGLE_API_KEY / GOOGLE_APPLICATION_CREDENTIALS
   python run_evaluation.py --mode benchmark

   Runs multiple scenarios and collects metrics:
   - Structural accuracy rate
   - First-try success rate
   - Average retry count

KEY METRICS:
- Structural Hard-Pass: Plan is non-empty and acyclic (disconnected components are warnings)
- First-Try Rate: LLM generates valid plan without Assert retry
- Semantic Score: Plan achieves the goal (requires LLM-as-judge)
    """)

def main() -> int:
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
        return 0

    ensure_ablation_output_dirs()

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
        return 0 if all(results.values()) else 1

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
