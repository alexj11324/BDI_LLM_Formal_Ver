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


def _eval_one(args: tuple) -> dict:
    """Evaluate a single plan in a worker process."""
    raw_plan, sample_data, split = args
    from bdi_llm.travelplanner.official import evaluate_travelplanner_plan

    plan_rows = raw_plan.get('submission', {}).get('plan', [])
    try:
        metrics = evaluate_travelplanner_plan(
            sample_data, plan_rows, travelplanner_home=_g_tp_home)
        result = dict(raw_plan)
        result['metrics'] = metrics.to_summary_dict()
        result['success'] = metrics.final_pass
        return result
    except Exception as exc:
        result = dict(raw_plan)
        result['metrics'] = {
            'delivery': bool(plan_rows),
            'commonsense_pass': False,
            'hard_constraint_pass': False,
            'final_pass': False,
            'commonsense_details': None,
            'hard_constraint_details': None,
        }
        result['success'] = False
        result['error'] = str(exc)
        return result


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

    # Match raw plans to samples by task_id (idx)
    eval_args = []
    for plan in raw_plans:
        task_id = plan.get('task_id', '')
        try:
            idx = int(task_id) - 1
        except (ValueError, TypeError):
            idx = raw_plans.index(plan)
        if 0 <= idx < len(samples):
            eval_args.append((plan, samples[idx], args.split))
        else:
            eval_args.append((plan, {}, args.split))

    tp_home = args.travelplanner_home or os.environ.get('TRAVELPLANNER_HOME', '')

    print(f"[{datetime.now():%H:%M:%S}] EVAL-ONLY split={args.split} mode={mode} "
          f"total={total} workers={args.workers}", flush=True)

    # Run evaluation with multiprocessing
    results = []
    completed = 0
    report_every = max(1, total // 20)

    with Pool(processes=args.workers,
              initializer=_init_evaluator,
              initargs=(tp_home,)) as pool:
        for result in pool.imap_unordered(_eval_one, eval_args, chunksize=4):
            results.append(result)
            completed += 1
            if completed % report_every == 0 or completed == total:
                success = sum(1 for r in results if r.get('success'))
                delivery = sum(1 for r in results if r.get('metrics', {}).get('delivery'))
                print(f"  [{args.split}/{mode}] eval {completed}/{total} "
                      f"delivery={delivery} success={success}", flush=True)

    # Sort results by task_id
    results.sort(key=lambda r: int(r.get('task_id', '0')))

    # Build summary
    from bdi_llm.travelplanner.official import summarize_travelplanner_results
    summary = summarize_travelplanner_results(results)

    out_dir = args.output_dir.resolve()
    mode_dir = out_dir / args.split / mode
    mode_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_path = mode_dir / f'results_travelplanner_{args.split}_{mode}_{stamp}.json'
    submission_path = mode_dir / f'submission_travelplanner_{args.split}_{mode}_{stamp}.jsonl'

    results_payload = {
        'split': args.split,
        'execution_mode': mode,
        'results': results,
        'summary': summary,
    }
    results_path.write_text(json.dumps(results_payload, indent=2, ensure_ascii=False))
    with submission_path.open('w', encoding='utf-8') as f:
        for row in results:
            f.write(json.dumps(row.get('submission', {}), ensure_ascii=False) + '\n')

    print(f"\n✅ Saved {len(results)} evaluated results → {results_path}")
    print(f"   Summary: {json.dumps(summary, indent=2)}", flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
