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
from src.bdi_llm.planner.domain_spec import (
    DomainSpec,
    extract_actions_from_pddl,
    extract_domain_name_from_pddl,
)
from src.bdi_llm.planning_task import PDDLPlanSerializer, PDDLTaskAdapter
from src.bdi_llm.verifier import PlanVerifier

logger = logging.getLogger(__name__)


def _determine_success(
    execution_mode: str,
    structural_valid: bool,
    val_valid: bool | None,
) -> bool:
    """Decide benchmark success without bypassing the DAG validity contract."""
    if execution_mode == "GENERATE_ONLY":
        return structural_valid
    return structural_valid and (val_valid is True)


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

                verifier = PDDLSymbolicVerifier()
                val_valid, val_errors = verifier.verify_plan(
                    domain_file=str(domain_pddl_path),
                    problem_file=str(problem_path),
                    plan_actions=actions,
                )
                result["val_valid"] = val_valid
                if not val_valid:
                    result["errors"].extend([f"[VAL] {e}" for e in val_errors])
            except Exception as val_exc:
                result["errors"].append(f"[VAL] {val_exc}")

        # 6. Determine overall success
        if execution_mode == "GENERATE_ONLY":
            result["success"] = result["structural_valid"]
        else:
            result["success"] = result["structural_valid"] and result.get("val_valid") is True

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
# Batch runner (parallel)
# ---------------------------------------------------------------------------


def _evaluate_worker(
    problem_path: Path,
    domain_pddl: Path,
    domain_name: str,
    domain_text: str,
    domain_context: str,
    execution_mode: str,
    param_order_map: dict[str, list[str]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Worker function for parallel evaluation. Creates its own planner instance."""
    from src.bdi_llm.planner.domain_spec import DomainSpec

    spec = DomainSpec.from_pddl(domain_name, domain_text)
    planner = BDIPlanner(auto_repair=True, domain_spec=spec)
    adapter = PDDLTaskAdapter(domain_name, domain_context)
    serializer = PDDLPlanSerializer(param_order_map=param_order_map)

    result: dict[str, Any] = {
        "task_id": problem_path.stem,
        "success": False,
        "structural_valid": False,
        "val_valid": None,
        "plan_actions": [],
        "errors": [],
        "duration_s": 0.0,
        "val_repair_attempts": 0,
        "val_repair_success": False,
        "one_shot": False,
    }

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
        task = adapter.to_planning_task(str(problem_path))
        raw_pred["beliefs"] = task.beliefs
        raw_pred["desire"] = task.desire
        raw_pred["domain_context"] = task.domain_context or ""
        logger.info(f"[{task.task_id}] Created planning task")

        pred = planner.generate_plan(
            beliefs=task.beliefs,
            desire=task.desire,
            domain_context=task.domain_context,
        )
        plan_obj = pred.plan
        raw_pred["raw_plan_text"] = str(pred.plan) if hasattr(pred, "plan") else ""

        if plan_obj is None:
            result["errors"].append("[Fatal] LLM returned no parseable plan (plan=None)")
            logger.error(f"[{task.task_id}] Plan is None — LLM parse failure")
            result["duration_s"] = round(time.time() - t0, 2)
            return result, raw_pred

        raw_pred["parse_success"] = True
        logger.info(f"[{task.task_id}] Plan generated ({len(plan_obj.nodes)} nodes)")

        actions = serializer.from_bdi_plan(plan_obj, task)
        result["plan_actions"] = actions

        G = plan_obj.to_networkx()
        is_valid, errors = PlanVerifier.verify(G)
        result["structural_valid"] = is_valid
        if not is_valid:
            result["errors"].extend([f"[Structural] {e}" for e in errors])

        if execution_mode == "VERIFY_WITH_VAL":
            try:
                from src.bdi_llm.symbolic_verifier import (
                    IntegratedVerifier,
                    PDDLSymbolicVerifier,
                )

                verifier = PDDLSymbolicVerifier()
                val_valid, val_errors = verifier.verify_plan(
                    domain_file=str(domain_pddl),
                    problem_file=str(problem_path),
                    plan_actions=actions,
                    verbose=True,
                )
                result["val_valid"] = val_valid

                if val_valid:
                    # First-attempt VAL pass = one-shot success
                    result["one_shot"] = True
                    logger.info(f"[{task.task_id}] VAL passed (one-shot)")
                else:
                    # ---- VAL repair loop (max 3 attempts) ----
                    max_val_repairs = 5
                    repair_attempt = 0
                    cumulative_history: list[dict] = []

                    while not val_valid and repair_attempt < max_val_repairs:
                        repair_attempt += 1
                        result["val_repair_attempts"] = repair_attempt

                        # Clean errors (strip verbose VAL output)
                        clean_errors = [e for e in val_errors if not e.lstrip().startswith("Full VAL output:")]
                        cumulative_history.append(
                            {
                                "attempt": repair_attempt,
                                "plan_actions": actions,
                                "val_errors": clean_errors,
                            }
                        )

                        try:
                            logger.info(f"[{task.task_id}] VAL repair {repair_attempt}/{max_val_repairs}")

                            # Build verification feedback
                            verification_context = {
                                "layers": {
                                    "structural": {
                                        "valid": is_valid,
                                        "errors": list(errors) if not is_valid else [],
                                    },
                                    "symbolic": {
                                        "valid": val_valid,
                                        "errors": clean_errors,
                                    },
                                },
                                "overall_valid": is_valid and val_valid,
                            }
                            failed_layers = [
                                n for n, l in verification_context["layers"].items() if not l.get("valid", False)
                            ]
                            verification_context["error_summary"] = (
                                f"Failed layers: {', '.join(failed_layers)}" if failed_layers else "All layers passed"
                            )
                            feedback = IntegratedVerifier.build_planner_feedback(verification_context)

                            repair_pred = planner.repair_from_val_errors(
                                beliefs=task.beliefs,
                                desire=task.desire,
                                previous_plan_actions=actions,
                                val_errors=clean_errors,
                                repair_history=cumulative_history,
                                verification_feedback=feedback,
                                instance_id=task.task_id,
                                domain=domain_name,
                                domain_context=task.domain_context or "",
                            )
                            plan_obj = repair_pred.plan
                            if plan_obj is None:
                                logger.warning(f"[{task.task_id}] VAL repair {repair_attempt}: returned None plan")
                                break

                            actions = serializer.from_bdi_plan(plan_obj, task)
                            result["plan_actions"] = actions

                            # Re-verify with VAL
                            val_valid, val_errors = verifier.verify_plan(
                                domain_file=str(domain_pddl),
                                problem_file=str(problem_path),
                                plan_actions=actions,
                                verbose=True,
                            )
                            result["val_valid"] = val_valid

                            if val_valid:
                                result["val_repair_success"] = True
                                logger.info(f"[{task.task_id}] VAL repair {repair_attempt}: SUCCESS")

                            # Update structural info
                            G = plan_obj.to_networkx()
                            s_valid, s_errors = PlanVerifier.verify(G)
                            is_valid = s_valid
                            errors = s_errors
                            result["structural_valid"] = s_valid

                        except Exception as repair_err:
                            logger.warning(
                                f"[{task.task_id}] VAL repair {repair_attempt} error: {str(repair_err)[:100]}"
                            )
                            continue

                    if not val_valid:
                        result["errors"].extend([f"[VAL] {e}" for e in val_errors])

            except Exception as val_exc:
                result["errors"].append(f"[VAL] {val_exc}")

        result["success"] = _determine_success(
            execution_mode=execution_mode,
            structural_valid=result["structural_valid"],
            val_valid=result.get("val_valid"),
        )

    except Exception as exc:
        import traceback

        tb = traceback.format_exc()
        result["errors"].append(f"[Fatal] {exc}")
        raw_pred["raw_plan_text"] = str(exc)
        logger.error(f"[{problem_path.stem}] Fatal error: {exc}\n{tb}")

    result["duration_s"] = round(time.time() - t0, 2)
    return result, raw_pred


def run_evaluation(
    domain_pddl: Path,
    problems: list[Path],
    execution_mode: str,
    output_dir: Path,
    max_workers: int = 20,
) -> list[dict[str, Any]]:
    """Run evaluation across PDDL problems with parallel workers."""
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    domain_text = domain_pddl.read_text()
    # Bug 3 fix: extract real domain name from PDDL header, fallback to file stem
    domain_name = extract_domain_name_from_pddl(domain_text) or domain_pddl.stem
    spec = DomainSpec.from_pddl(domain_name, domain_text)
    domain_context = spec.domain_context or ""

    # Bug 2 fix: build param_order_map from domain schema for deterministic serialization
    actions_schema = extract_actions_from_pddl(domain_text)
    param_order_map = {a["name"]: [p[0] for p in a["parameters"]] for a in actions_schema}

    output_dir.mkdir(parents=True, exist_ok=True)
    predictions_path = output_dir / "raw_predictions.jsonl"

    results: list[dict[str, Any]] = [None] * len(problems)  # preserve order
    write_lock = threading.Lock()
    completed = [0]

    total = len(problems)
    print(f"\nStarting parallel evaluation: {total} problems, {max_workers} workers")

    with open(predictions_path, "w") as pred_f:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {}
            for idx, problem_path in enumerate(problems):
                future = executor.submit(
                    _evaluate_worker,
                    problem_path=problem_path,
                    domain_pddl=domain_pddl,
                    domain_name=domain_name,
                    domain_text=domain_text,
                    domain_context=domain_context,
                    execution_mode=execution_mode,
                    param_order_map=param_order_map,
                )
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result, raw_pred = future.result()
                except Exception as exc:
                    result = {
                        "task_id": problems[idx].stem,
                        "success": False,
                        "errors": [f"[Worker] {exc}"],
                    }
                    raw_pred = {"task_id": problems[idx].stem, "parse_success": False}

                results[idx] = result

                with write_lock:
                    pred_f.write(json.dumps(raw_pred, ensure_ascii=False) + "\n")
                    pred_f.flush()
                    completed[0] += 1
                    if completed[0] % 10 == 0 or completed[0] == total:
                        ok = sum(1 for r in results if r and r.get("success"))
                        print(f"  Progress: {completed[0]}/{total} done, {ok} success so far")

    # Write results.json
    results_path = output_dir / "results.json"
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    # Write summary.json
    success = sum(1 for r in results if r and r.get("success"))
    one_shot = sum(1 for r in results if r and r.get("one_shot"))
    repaired = sum(1 for r in results if r and r.get("val_repair_success"))
    failed = total - success
    summary = {
        "domain": domain_name,
        "execution_mode": execution_mode,
        "total": total,
        "success": success,
        "one_shot": one_shot,
        "repaired": repaired,
        "failed": failed,
        "success_rate": f"{success / total * 100:.1f}%" if total else "N/A",
        "one_shot_rate": f"{one_shot / total * 100:.1f}%" if total else "N/A",
        "timestamp": output_dir.name,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    print(f"\n{'=' * 60}")
    print(f"Domain: {domain_name} | Mode: {execution_mode}")
    print(f"Results: {success}/{total} ({summary['success_rate']})")
    print(f"  One-shot: {one_shot} | Repaired: {repaired} | Failed: {failed}")
    print(f"Output: {output_dir}")
    print("  summary.json | results.json | raw_predictions.jsonl")
    print(f"{'=' * 60}")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Generic PDDL evaluation runner for BDI planner")
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
        "--workers",
        type=int,
        default=20,
        help="Number of parallel workers (default: 20)",
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

    if args.output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.output_dir = PROJECT_ROOT / "runs" / "generic_pddl_eval" / timestamp

    problems: list[Path] = []
    if args.problem_pddl:
        if not args.problem_pddl.exists():
            parser.error(f"Problem file not found: {args.problem_pddl}")
        problems.append(args.problem_pddl)
    elif args.problem_dir:
        if not args.problem_dir.is_dir():
            parser.error(f"Problem directory not found: {args.problem_dir}")
        problems = sorted(p for p in args.problem_dir.glob("*.pddl") if "domain" not in p.stem.lower())
        if not problems:
            parser.error(f"No problem files found in: {args.problem_dir}")
    else:
        parser.error("Must specify either --problem_pddl or --problem_dir")

    run_evaluation(
        domain_pddl=args.domain_pddl,
        problems=problems,
        execution_mode=args.execution_mode,
        output_dir=args.output_dir,
        max_workers=args.workers,
    )


if __name__ == "__main__":
    main()
