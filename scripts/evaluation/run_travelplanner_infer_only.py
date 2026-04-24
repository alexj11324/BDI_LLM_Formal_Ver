#!/usr/bin/env python3
"""Phase 1: LLM inference only — generates raw plans, NO evaluation.

Saves raw_plans_{split}_{mode}_{timestamp}.json containing each sample's
raw plan + submission but NO metrics.  This is I/O-bound and fast.

Usage:
  python scripts/evaluation/run_travelplanner_infer_only.py \
    --split test --mode baseline --output_dir runs/tp_infer \
    --workers 1000
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

# -- bootstrap project --
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluation._travelplanner_threading import iter_bounded_indexed_results
from src.bdi_llm.planner.dspy_config import configure_dspy
from src.bdi_llm.travelplanner.official import load_travelplanner_split
from src.bdi_llm.travelplanner.runner import generate_submission


def infer_sample(sample: dict, *, mode: str) -> dict:
    """Run LLM inference only — no evaluation."""
    workflow = generate_submission(sample, mode)
    return {
        "task_id": workflow["task"].task_id,
        "query": sample.get("query", ""),
        "mode": mode,
        "prompt_version": workflow.get("prompt_version"),
        "submission": workflow["submission"],
        "itinerary": workflow["final_itinerary"].model_dump(),
        "non_oracle_diagnostics": workflow.get("non_oracle_diagnostics", {}),
    }


def _failure_payload(sample: dict, mode: str, exc: Exception) -> dict:
    sample_idx = sample.get("idx", 0)
    return {
        "task_id": str(sample_idx),
        "query": sample.get("query", ""),
        "mode": mode,
        "submission": {"idx": sample_idx, "query": sample.get("query", ""), "plan": []},
        "itinerary": {},
        "error": str(exc),
    }


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--split", default="test")
    parser.add_argument("--mode", default="baseline", choices=["baseline", "bdi"])
    parser.add_argument("--output_dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=200)
    parser.add_argument("--max_instances", type=int, default=None)
    args = parser.parse_args()

    configure_dspy()
    data = load_travelplanner_split(args.split)
    if args.max_instances:
        data = data[: args.max_instances]

    for idx, s in enumerate(data, 1):
        s["idx"] = idx
        s["split"] = args.split

    total = len(data)
    out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"[{datetime.now():%H:%M:%S}] INFER-ONLY split={args.split} mode={args.mode} "
        f"total={total} workers={args.workers}",
        flush=True,
    )

    results = [None] * total
    completed = 0
    report_every = max(1, total // 20)

    def process(i: int, sample: dict) -> dict:
        try:
            return infer_sample(sample, mode=args.mode)
        except Exception as exc:
            return _failure_payload(sample, args.mode, exc)

    for idx, result in iter_bounded_indexed_results(
        enumerate(data),
        process,
        max_workers=args.workers,
    ):
        results[idx] = result
        completed += 1
        if completed % report_every == 0 or completed == total:
            print(f"  [{args.split}/{args.mode}] infer {completed}/{total}", flush=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = out_dir / f"raw_plans_{args.split}_{args.mode}_{stamp}.json"
    payload = {
        "split": args.split,
        "mode": args.mode,
        "total": total,
        "raw_plans": [r for r in results if r is not None],
    }
    out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    print(f"\n✅ Saved {len(payload['raw_plans'])} raw plans → {out_file}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
