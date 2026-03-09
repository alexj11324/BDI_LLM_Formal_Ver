#!/usr/bin/env python3
"""Phase 2: Evaluate raw plans using multiprocessing (CPU-bound).

Reads raw_plans JSON from Phase 1 and runs commonsense + hard constraint
evaluation in parallel using multiprocessing.Pool (bypasses GIL).

Usage (on server):
  python scripts/evaluation/run_travelplanner_eval_only.py \
    --raw_plans raw_plans_test_baseline_*.json \
    --split test \
    --travelplanner_home /path/to/TravelPlanner \
    --workers 4 \
    --output_dir runs/tp_results
"""
from __future__ import annotations

import json, sys, traceback, os
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path

# -- bootstrap project --
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))


def _init_evaluator(tp_home: str | None):
    """Initialize evaluator in each worker process (loads DB once per process)."""
    global _g_tp_home
    from bdi_llm.travelplanner.official import load_official_evaluator, resolve_travelplanner_home

    _g_tp_home = str(resolve_travelplanner_home(tp_home))
    load_official_evaluator(Path(_g_tp_home))


def _resolve_plan_sample_index(raw_plan: dict, input_order: int) -> int:
    for candidate in (
        raw_plan.get('task_id'),
        (raw_plan.get('submission') or {}).get('idx'),
    ):
        try:
            return int(candidate) - 1
        except (TypeError, ValueError):
            continue
    return input_order


def _eval_one(args: tuple[int, dict, dict]) -> tuple[int, dict]:
    """Evaluate a single plan in a worker process."""
    input_order, raw_plan, sample_data = args
    from bdi_llm.travelplanner.official import TravelPlannerEvalResult, evaluate_travelplanner_plan

    plan_rows = raw_plan.get('submission', {}).get('plan', [])
    try:
        metrics = evaluate_travelplanner_plan(
            sample_data, plan_rows, travelplanner_home=_g_tp_home)
        result = dict(raw_plan)
        result['metrics'] = metrics.to_summary_dict()
        result['success'] = metrics.final_pass
        return input_order, result
    except Exception as exc:
        fallback_metrics = TravelPlannerEvalResult(
            delivery=bool(plan_rows),
            commonsense_pass=False,
            hard_constraint_pass=False,
            final_pass=False,
            commonsense_details=None,
            hard_constraint_details=None,
        )
        result = dict(raw_plan)
        result['metrics'] = fallback_metrics.to_summary_dict()
        result['success'] = False
        result['error'] = str(exc)
        return input_order, result


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--raw_plans', type=Path, required=True,
                        help='Path to raw_plans JSON from Phase 1')
    parser.add_argument('--split', default='test')
    parser.add_argument('--travelplanner_home', type=str, default=None,
                        help='Path to TravelPlanner repo (with database/)')
    parser.add_argument('--workers', type=int, default=None,
                        help='Number of worker processes (default: cpu_count)')
    parser.add_argument('--output_dir', type=Path, required=True)
    args = parser.parse_args()

    if args.workers is None:
        args.workers = os.cpu_count() or 4

    # Load raw plans
    with open(args.raw_plans) as f:
        raw_data = json.load(f)

    raw_plans = raw_data['raw_plans']
    mode = raw_data['mode']
    total = len(raw_plans)

    # Load dataset for evaluation context
    from bdi_llm.travelplanner.official import load_travelplanner_split

    samples = [dict(row) for row in load_travelplanner_split(args.split)]

    # Match raw plans to samples using stable input order fallback.
    eval_args = []
    for input_order, plan in enumerate(raw_plans):
        sample_index = _resolve_plan_sample_index(plan, input_order)
        if 0 <= sample_index < len(samples):
            sample = samples[sample_index]
        else:
            sample = {}
        eval_args.append((input_order, plan, sample))

    tp_home = args.travelplanner_home or os.environ.get('TRAVELPLANNER_HOME', '')

    print(f"[{datetime.now():%H:%M:%S}] EVAL-ONLY split={args.split} mode={mode} "
          f"total={total} workers={args.workers}", flush=True)

    # Run evaluation with multiprocessing
    results: list[dict | None] = [None] * total
    completed = 0
    delivered = 0
    succeeded = 0
    report_every = max(1, total // 20)

    with Pool(processes=args.workers,
              initializer=_init_evaluator,
              initargs=(tp_home,)) as pool:
        for input_order, result in pool.imap_unordered(_eval_one, eval_args, chunksize=4):
            results[input_order] = result
            completed += 1
            delivered += int(bool(result.get('metrics', {}).get('delivery')))
            succeeded += int(bool(result.get('success')))
            if completed % report_every == 0 or completed == total:
                print(f"  [{args.split}/{mode}] eval {completed}/{total} "
                      f"delivery={delivered} success={succeeded}", flush=True)

    ordered_results = [row for row in results if row is not None]

    # Build summary
    from bdi_llm.travelplanner.official import summarize_travelplanner_results
    summary = summarize_travelplanner_results(ordered_results)

    out_dir = args.output_dir.resolve()
    mode_dir = out_dir / args.split / mode
    mode_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_path = mode_dir / f'results_travelplanner_{args.split}_{mode}_{stamp}.json'
    submission_path = mode_dir / f'submission_travelplanner_{args.split}_{mode}_{stamp}.jsonl'

    results_payload = {
        'split': args.split,
        'execution_mode': mode,
        'results': ordered_results,
        'summary': summary,
    }
    results_path.write_text(json.dumps(results_payload, indent=2, ensure_ascii=False))
    with submission_path.open('w', encoding='utf-8') as f:
        for row in ordered_results:
            f.write(json.dumps(row.get('submission', {}), ensure_ascii=False) + '\n')

    print(f"\n✅ Saved {len(ordered_results)} evaluated results → {results_path}")
    print(f"   Summary: {json.dumps(summary, indent=2)}", flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
