#!/usr/bin/env python3
"""Batch runner for SWE-bench local harness with checkpoint/resume."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from swe_bench_harness import LocalSWEBenchHarness

load_dotenv()


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
    os.replace(tmp, path)


def has_api_credentials() -> bool:
    return bool(
        os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    )


def load_instance_ids(args: argparse.Namespace, harness: LocalSWEBenchHarness) -> List[str]:
    if args.instances_file:
        file_path = Path(args.instances_file)
        if not file_path.exists():
            raise FileNotFoundError(f"Instance file not found: {file_path}")
        return [line.strip() for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    ids = [item["instance_id"] for item in harness.dataset]
    if args.limit is not None:
        ids = ids[: args.limit]
    return ids


def summarize(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    status_counter: Counter[str] = Counter()
    error_counter: Counter[str] = Counter()
    duration_values: List[float] = []

    for row in results:
        status_counter[str(row.get("status", "unknown"))] += 1
        category = row.get("error_category")
        if category:
            error_counter[str(category)] += 1
        duration = row.get("durations_sec", {}).get("total")
        if isinstance(duration, (int, float)):
            duration_values.append(float(duration))

    passed = status_counter.get("passed", 0)
    failed = total - passed
    avg_duration = (sum(duration_values) / len(duration_values)) if duration_values else 0.0

    return {
        "total_instances": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": (passed / total) if total else 0.0,
        "status_counts": dict(status_counter),
        "error_taxonomy": dict(error_counter),
        "avg_duration_sec": avg_duration,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SWE-bench local harness in batch mode.")
    parser.add_argument(
        "--output_dir",
        type=str,
        default="runs/swe_bench_results",
        help="Directory for run outputs (results/checkpoint/per-instance artifacts).",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default="swe_bench_workspace",
        help="Workspace directory for cloned repos.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max number of instances when --instances_file is not provided (default: 50).",
    )
    parser.add_argument(
        "--instances_file",
        type=str,
        default=None,
        help="Optional text file of instance IDs (one per line).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint in output_dir if it exists.",
    )
    parser.add_argument(
        "--checkpoint_every",
        type=int,
        default=1,
        help="Persist checkpoint every N completed instances (default: 1).",
    )
    parser.add_argument(
        "--test_timeout",
        type=int,
        default=600,
        help="Timeout in seconds for each test command (default: 600).",
    )
    parser.add_argument(
        "--setup_timeout",
        type=int,
        default=900,
        help="Timeout in seconds for repository clone/setup operations (default: 900).",
    )
    parser.add_argument(
        "--max_plan_steps",
        type=int,
        default=40,
        help="Maximum number of plan steps to execute per instance (default: 40).",
    )
    parser.add_argument(
        "--keep_workspace",
        action="store_true",
        help="Keep per-instance repository workspaces after execution.",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Resolve instance set and emit planned outputs without execution.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    instances_dir = out_dir / "instances"
    checkpoint_path = out_dir / "checkpoint.json"
    results_path = out_dir / "results.json"
    summary_path = out_dir / "summary.json"
    taxonomy_path = out_dir / "error_taxonomy.json"

    if args.checkpoint_every < 1:
        args.checkpoint_every = 1

    if not args.dry_run and not has_api_credentials():
        print("ERROR: No API credential found for SWE-bench batch run.")
        return 1

    harness = LocalSWEBenchHarness(workspace_dir=args.workspace)
    all_ids = load_instance_ids(args, harness)

    state: Dict[str, Any] = {
        "schema_version": 1,
        "run_id": f"swe_bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "created_at": now_utc(),
        "updated_at": now_utc(),
        "config": vars(args),
        "total_planned": len(all_ids),
        "results": [],
    }
    completed_ids = set()

    if args.resume and checkpoint_path.exists():
        state = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        state["updated_at"] = now_utc()
        state["config"] = vars(args)
        completed_ids = {str(row.get("instance_id")) for row in state.get("results", []) if row.get("instance_id")}
        print(f"Resuming from {checkpoint_path} ({len(completed_ids)} completed)")

    pending_ids = [instance_id for instance_id in all_ids if instance_id not in completed_ids]
    print(f"Running SWE-bench batch: total={len(all_ids)}, pending={len(pending_ids)}")

    for idx, instance_id in enumerate(pending_ids, start=1):
        print(f"[{idx}/{len(pending_ids)}] {instance_id}")
        record: Dict[str, Any]

        if args.dry_run:
            record = {
                "instance_id": instance_id,
                "status": "planned",
                "tests_passed": False,
                "error_category": None,
                "durations_sec": {"total": 0.0},
            }
        else:
            try:
                record = harness.run_instance(
                    instance_id=instance_id,
                    test_timeout=args.test_timeout,
                    max_plan_steps=args.max_plan_steps,
                    setup_timeout=args.setup_timeout,
                    keep_workspace=args.keep_workspace,
                )
            except Exception as exc:
                record = {
                    "instance_id": instance_id,
                    "status": "runner_error",
                    "tests_passed": False,
                    "error": str(exc),
                    "error_category": "runner_error",
                    "durations_sec": {"total": 0.0},
                }

        record["recorded_at"] = now_utc()
        state["results"].append(record)

        instance_artifact = instances_dir / instance_id
        instance_artifact.mkdir(parents=True, exist_ok=True)
        diff_text = str(record.pop("git_diff", "")) if "git_diff" in record else ""
        (instance_artifact / "metadata.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        (instance_artifact / "test_output_tail.log").write_text(
            str(record.get("final_test_output_tail", "")),
            encoding="utf-8",
        )
        (instance_artifact / "git.diff").write_text(diff_text, encoding="utf-8")

        if len(state["results"]) % args.checkpoint_every == 0:
            state["updated_at"] = now_utc()
            write_json_atomic(checkpoint_path, state)

    state["updated_at"] = now_utc()
    write_json_atomic(checkpoint_path, state)

    summary = summarize(state["results"])
    summary_payload = {
        "timestamp": now_utc(),
        "run_id": state["run_id"],
        "total_planned": len(all_ids),
        **summary,
    }
    write_json_atomic(summary_path, summary_payload)
    write_json_atomic(taxonomy_path, {"timestamp": now_utc(), "error_taxonomy": summary["error_taxonomy"]})
    write_json_atomic(
        results_path,
        {
            "timestamp": now_utc(),
            "run_id": state["run_id"],
            "config": state["config"],
            "summary": summary_payload,
            "results": state["results"],
        },
    )

    print("SWE-bench batch complete")
    print(
        f"  pass: {summary_payload['passed']}/{summary_payload['total_instances']} "
        f"({summary_payload['pass_rate']:.2%})"
    )
    print(f"  results: {results_path}")
    print(f"  summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
