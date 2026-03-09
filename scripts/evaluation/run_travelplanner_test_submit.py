#!/usr/bin/env python3
"""Generate TravelPlanner test set plans for leaderboard submission.

Outputs JSONL matching the official TravelPlanner submission format:
  {"idx": N, "query": "...", "plan": [{day fields...}, ...]}

This script uses the same sole-planning generation path as the validation
runner's non-oracle inference flow. It does not use a test-only dummy repair
heuristic.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / '.env')

from src.bdi_llm.planner.dspy_config import configure_dspy
configure_dspy()

from src.bdi_llm.travelplanner.official import load_travelplanner_split
from src.bdi_llm.travelplanner.runner import generate_submission


def generate_plan(sample: dict, idx: int, mode: str) -> dict:
    enriched = dict(sample)
    enriched['idx'] = idx
    enriched['split'] = 'test'
    workflow = generate_submission(enriched, mode)
    return {
        'submission': workflow['submission'],
        'diagnostics': {
            'prompt_version': workflow.get('prompt_version'),
            'non_oracle_diagnostics': workflow.get('non_oracle_diagnostics', {}),
        },
    }


def main():
    parser = argparse.ArgumentParser(description='Generate TravelPlanner test plans for leaderboard')
    parser.add_argument('--mode', required=True, choices=['baseline', 'bdi', 'bdi-repair'])
    parser.add_argument('--output_dir', default='runs/tp_test_submit')
    parser.add_argument('--workers', type=int, default=100)
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading test split...", flush=True)
    data = load_travelplanner_split('test')
    total = len(data)
    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] Loaded {total} test samples. "
        f"Mode={args.mode}, Workers={args.workers}",
        flush=True,
    )

    submissions: list[dict | None] = [None] * total
    diagnostics_rows: list[dict | None] = [None] * total
    completed = 0

    checkpoint_path = out_dir / f"checkpoint_{args.mode}.json"
    diagnostics_path = out_dir / f"diagnostics_{args.mode}.json"
    submission_path = out_dir / f"submission_{args.mode}.jsonl"
    leaderboard_submission_path = out_dir / f"test_soleplanning_{args.mode}.jsonl"

    done_indices = set()
    if checkpoint_path.exists():
        saved = json.loads(checkpoint_path.read_text())
        for record in saved:
            if record is None:
                continue
            if 'submission' in record:
                submission = record['submission']
                diagnostics = record.get('diagnostics', {})
            else:
                submission = record
                diagnostics = {}
            idx = int(submission['idx']) - 1
            submissions[idx] = submission
            diagnostics_rows[idx] = diagnostics
            done_indices.add(idx)
        completed = len(done_indices)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Resumed {completed}/{total} from checkpoint", flush=True)

    def process(i: int):
        if i in done_indices:
            return i, {
                'submission': submissions[i],
                'diagnostics': diagnostics_rows[i] or {},
            }
        try:
            return i, generate_plan(data[i], i + 1, args.mode)
        except Exception:
            traceback.print_exc()
            return i, {
                'submission': {'idx': i + 1, 'query': data[i].get('query', ''), 'plan': []},
                'diagnostics': {'error': 'generation_failed'},
            }

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process, i): i for i in range(total)}
        for fut in as_completed(futures):
            i, result = fut.result()
            submissions[i] = result['submission']
            diagnostics_rows[i] = result.get('diagnostics', {})
            completed += 1
            if completed % 10 == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] [{args.mode}] {completed}/{total}", flush=True)
                checkpoint_payload = [
                    {'submission': s, 'diagnostics': d}
                    for s, d in zip(submissions, diagnostics_rows)
                    if s is not None
                ]
                checkpoint_path.write_text(json.dumps(checkpoint_payload, ensure_ascii=False))

    for path in (submission_path, leaderboard_submission_path):
        with path.open('w', encoding='utf-8') as f:
            for record in submissions:
                if record is not None:
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')

    diagnostics_payload = [
        {'submission': s, 'diagnostics': d}
        for s, d in zip(submissions, diagnostics_rows)
        if s is not None
    ]
    checkpoint_path.write_text(json.dumps(diagnostics_payload, indent=2, ensure_ascii=False))
    diagnostics_path.write_text(json.dumps(diagnostics_payload, indent=2, ensure_ascii=False))

    print(
        f"[{datetime.now().strftime('%H:%M:%S')}] DONE. Saved {submission_path} and "
        f"{leaderboard_submission_path} ({total} plans)",
        flush=True,
    )
    plans_ok = sum(1 for r in submissions if r and len(r.get('plan', [])) > 0)
    print(f"  Plans with content: {plans_ok}/{total}", flush=True)
    if args.mode == 'bdi-repair':
        triggered = sum(
            1
            for row in diagnostics_rows
            if (row or {}).get('non_oracle_diagnostics', {}).get('triggered')
        )
        print(f"  Non-oracle repair triggered: {triggered}/{total}", flush=True)


if __name__ == '__main__':
    main()
