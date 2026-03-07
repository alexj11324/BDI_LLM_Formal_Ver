#!/usr/bin/env python3
"""Generic PDDL evaluation runner.

Usage examples
--------------
Single problem::

    python scripts/evaluation/run_generic_pddl_eval.py \\
        --domain_pddl tests/fixtures/gripper/domain.pddl \\
        --problem_pddl tests/fixtures/gripper/problem1.pddl

Problem directory (batch)::

    python scripts/evaluation/run_generic_pddl_eval.py \\
        --domain_pddl tests/fixtures/gripper/domain.pddl \\
        --problem_dir tests/fixtures/gripper/

Execution modes
---------------
* ``GENERATE_ONLY``  – run planner + structural verification only
* ``VERIFY_WITH_VAL`` – additionally run PDDL symbolic verification via VAL
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.bdi_llm.planner import BDIPlanner
from src.bdi_llm.planner.domain_spec import DomainSpec
from src.bdi_llm.planning_task import PDDLPlanSerializer, PDDLTaskAdapter
from src.bdi_llm.verifier import PlanVerifier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core evaluation function
# ---------------------------------------------------------------------------

def evaluate_single_problem(
    planner: BDIPlanner,
    task_adapter: PDDLTaskAdapter,
    serializer: PDDLPlanSerializer,
    problem_path: Path,
    domain_pddl_path: Path,
    execution_mode: str,
    predictions_file,
) -> dict[str, Any]:
    """Evaluate a single PDDL problem instance.

    Returns a result dict and writes a line to raw_predictions.jsonl.
    """
    result: dict[str, Any] = {
        "task_id": problem_path.stem,
        "success": False,
        "structural_valid": False,
        "val_valid": None,
        "plan_actions": [],
        "errors": [],
        "duration_s": 0.0,
    }

    # raw_predictions record — §4.7 fixed schema
    raw_pred: dict[str, Any] = {
        "task_id": problem_path.stem,
        "beliefs": "",
        "desire": "",
        "domain_context": "",
        "raw_plan_text": "",
        "parse_success": False,
    }

    t0 = time.time()

    try:
        # 1. Convert problem to PlanningTask
        task = task_adapter.to_planning_task(str(problem_path))
        raw_pred["beliefs"] = task.beliefs
        raw_pred["desire"] = task.desire
        raw_pred["domain_context"] = task.domain_context or ""
        logger.info(f"[{task.task_id}] Created planning task")

        # 2. Generate plan
        pred = planner.generate_plan(
            beliefs=task.beliefs,
            desire=task.desire,
            domain_context=task.domain_context,
        )
        plan_obj = pred.plan
        raw_pred["raw_plan_text"] = str(pred.plan) if hasattr(pred, "plan") else ""
        raw_pred["parse_success"] = True
        logger.info(f"[{task.task_id}] Plan generated ({len(plan_obj.nodes)} nodes)")

        # 3. Serialize plan actions
        actions = serializer.from_bdi_plan(plan_obj, task)
        result["plan_actions"] = actions

        # 4. Structural verification
        G = plan_obj.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)
        result["structural_valid"] = is_valid
        if not is_valid:
            result["errors"].extend([f"[Structural] {e}" for e in errors])

        # 5. VAL verification (if requested)
        if execution_mode == "VERIFY_WITH_VAL":
            try:
                from src.bdi_llm.symbolic_verifier import PDDLSymbolicVerifier

                verifier = PDDLSymbolicVerifier(
                    domain_file=str(domain_pddl_path),
                    problem_file=str(problem_path),
                )
                val_result = verifier.verify_plan(actions)
                result["val_valid"] = val_result.get("valid", False)
                if not val_result.get("valid", False):
                    val_errors = val_result.get("errors", [])
                    result["errors"].extend([f"[VAL] {e}" for e in val_errors])
            except Exception as val_exc:
                result["errors"].append(f"[VAL] {val_exc}")

        # 6. Determine overall success
        if execution_mode == "GENERATE_ONLY":
            result["success"] = result["structural_valid"]
        else:
            result["success"] = (
                result["structural_valid"] and result.get("val_valid") is True
            )

    except Exception as exc:
        result["errors"].append(f"[Fatal] {exc}")
        raw_pred["raw_plan_text"] = str(exc)
        logger.error(f"[{problem_path.stem}] Fatal error: {exc}")

    result["duration_s"] = round(time.time() - t0, 2)

    # Write raw prediction line (§4.7)
    predictions_file.write(json.dumps(raw_pred, ensure_ascii=False) + "\n")
    predictions_file.flush()

    return result


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def run_evaluation(
    domain_pddl: Path,
    problems: list[Path],
    execution_mode: str,
    output_dir: Path,
) -> list[dict[str, Any]]:
    """Run evaluation across a set of PDDL problems."""
    # Build DomainSpec from PDDL
    domain_text = domain_pddl.read_text()
    domain_name = domain_pddl.stem
    spec = DomainSpec.from_pddl(domain_name, domain_text)

    # Create planner and adapters
    planner = BDIPlanner(auto_repair=True, domain_spec=spec)
    adapter = PDDLTaskAdapter(domain_name, spec.domain_context)
    serializer = PDDLPlanSerializer()

    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    predictions_path = output_dir / "raw_predictions.jsonl"

    with open(predictions_path, "w") as pred_f:
        for problem_path in problems:
            logger.info(f"Evaluating: {problem_path.name}")
            result = evaluate_single_problem(
                planner=planner,
                task_adapter=adapter,
                serializer=serializer,
                problem_path=problem_path,
                domain_pddl_path=domain_pddl,
                execution_mode=execution_mode,
                predictions_file=pred_f,
            )
            results.append(result)

    # Write results.json (all results array)
    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    # Write summary.json
    total = len(results)
    success = sum(1 for r in results if r["success"])
    summary = {
        "domain": domain_name,
        "execution_mode": execution_mode,
        "total": total,
        "success": success,
        "success_rate": f"{success / total * 100:.1f}%" if total else "N/A",
        "timestamp": output_dir.name,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print(f"\n{'=' * 60}")
    print(f"Domain: {domain_name} | Mode: {execution_mode}")
    print(f"Results: {success}/{total} ({summary['success_rate']})")
    print(f"Output: {output_dir}")
    print(f"  summary.json | results.json | raw_predictions.jsonl")
    print(f"{'=' * 60}")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generic PDDL evaluation runner for BDI planner"
    )
    parser.add_argument(
        "--domain_pddl",
        type=Path,
        required=True,
        help="Path to PDDL domain file",
    )
    parser.add_argument(
        "--problem_pddl",
        type=Path,
        default=None,
        help="Path to a single PDDL problem file",
    )
    parser.add_argument(
        "--problem_dir",
        type=Path,
        default=None,
        help="Directory containing PDDL problem files (*.pddl)",
    )
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=None,
        help="Output directory (default: runs/generic_pddl_eval/<timestamp>/)",
    )
    parser.add_argument(
        "--execution_mode",
        choices=["GENERATE_ONLY", "VERIFY_WITH_VAL"],
        default="GENERATE_ONLY",
        help="Execution mode: GENERATE_ONLY or VERIFY_WITH_VAL",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.domain_pddl.exists():
        parser.error(f"Domain file not found: {args.domain_pddl}")

    # §4.4: default output directory convention
    if args.output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output_dir = PROJECT_ROOT / "runs" / "generic_pddl_eval" / timestamp

    # Collect problems
    problems: list[Path] = []
    if args.problem_pddl:
        if not args.problem_pddl.exists():
            parser.error(f"Problem file not found: {args.problem_pddl}")
        problems.append(args.problem_pddl)
    elif args.problem_dir:
        if not args.problem_dir.is_dir():
            parser.error(f"Problem directory not found: {args.problem_dir}")
        problems = sorted(
            p for p in args.problem_dir.glob("*.pddl")
            if "domain" not in p.stem.lower()
        )
        if not problems:
            parser.error(f"No problem files found in: {args.problem_dir}")
    else:
        parser.error("Must specify either --problem_pddl or --problem_dir")

    run_evaluation(
        domain_pddl=args.domain_pddl,
        problems=problems,
        execution_mode=args.execution_mode,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
