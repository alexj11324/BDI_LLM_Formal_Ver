#!/usr/bin/env python3
"""
Adaptive Batch Benchmark Runner
================================

Strategy:
  1. Run initial batch of N instances (default: 100)
  2. Count failures
  3. If failures >= threshold (default: 50) → stop, output failed list
  4. If failures < threshold → gap = threshold - failures
     Run 2 * gap more instances (next batch)
  5. Repeat until threshold met or all instances exhausted

Uses existing checkpoint/resume mechanism from run_planbench_full.py.

Usage:
    python scripts/evaluation/run_adaptive_benchmark.py \
      --domain logistics \
      --initial_batch 100 \
      --failure_threshold 50 \
      --output_dir runs/iter_logistics
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")


def count_failures(checkpoint_file: str) -> tuple[int, int, int]:
    """Read checkpoint and return (total_evaluated, success_count, failed_count)."""
    if not os.path.exists(checkpoint_file):
        return 0, 0, 0
    try:
        with open(checkpoint_file, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return 0, 0, 0
    results = data.get('results', [])
    total = len(results)
    success = sum(1 for r in results if r.get('success', False))
    failed = total - success
    return total, success, failed


def extract_failed_instances(checkpoint_file: str, output_file: str) -> list[str]:
    """Extract failed instance paths from checkpoint and save to file."""
    with open(checkpoint_file, 'r') as f:
        data = json.load(f)
    failed = [
        r.get('instance_file', '<unknown>') for r in data.get('results', [])
        if not r.get('success', False)
    ]
    with open(output_file, 'w') as f:
        f.write('\n'.join(failed))
    return failed


def run_batch(domain: str, max_instances: int, output_dir: str,
              execution_mode: str = "BDI_REPAIR",
              parallel: bool = True, workers: int = 100) -> int:
    """Run a batch of benchmark instances. Returns exit code."""
    cmd = [
        sys.executable,
        str(Path(__file__).parent / "run_planbench_full.py"),
        "--domain", domain,
        "--max_instances", str(max_instances),
        "--execution_mode", execution_mode,
        "--output_dir", output_dir,
    ]
    if parallel:
        cmd.extend(["--parallel", "--workers", str(workers)])
    print(f"\n{'='*60}")
    print(f"  Running batch: {max_instances} instances (domain={domain})")
    print(f"  Command: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent.parent.parent),
                            env=os.environ.copy())
    return result.returncode


def main():
    parser = argparse.ArgumentParser(
        description="Adaptive Batch Benchmark: run until enough failures collected"
    )
    parser.add_argument("--domain", type=str, required=True,
                        choices=["blocksworld", "logistics", "depots"])
    parser.add_argument("--initial_batch", type=int, default=100,
                        help="Initial batch size (default: 100)")
    parser.add_argument("--failure_threshold", type=int, default=50,
                        help="Stop when this many failures accumulated (default: 50)")
    parser.add_argument("--output_dir", type=str, default="runs/planbench_results",
                        help="Output directory")
    parser.add_argument("--execution_mode", type=str, default="BDI_REPAIR",
                        choices=["BASELINE", "BDI", "BDI_REPAIR"])
    parser.add_argument("--parallel", dest="parallel", action="store_true",
                        help="Run instances in parallel")
    parser.add_argument("--no-parallel", dest="parallel", action="store_false",
                        help="Run instances serially")
    parser.set_defaults(parallel=True)
    parser.add_argument("--workers", type=int, default=100,
                        help="Number of parallel workers (default: 100)")
    parser.add_argument("--max_rounds", type=int, default=10,
                        help="Max adaptive rounds to prevent infinite loop (default: 10)")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    checkpoint_file = f"{args.output_dir}/checkpoint_{args.domain}.json"
    failed_file = f"{args.output_dir}/failed_instances_{args.domain}.txt"

    # Check if there's already a checkpoint (resume scenario)
    total_prev, _, failed_prev = count_failures(checkpoint_file)
    if failed_prev >= args.failure_threshold:
        print(f"✅ Already have {failed_prev} failures (≥ {args.failure_threshold})")
        print(f"   Extracting failed instances...")
        failed_list = extract_failed_instances(checkpoint_file, failed_file)
        print(f"   {len(failed_list)} failed instances saved to: {failed_file}")
        return

    # Adaptive batch loop
    cumulative_max = total_prev + args.initial_batch  # First batch
    round_num = 0

    while round_num < args.max_rounds:
        round_num += 1

        print(f"\n{'#'*60}")
        print(f"  ADAPTIVE ROUND {round_num}")
        print(f"  Cumulative max instances: {cumulative_max}")
        print(f"{'#'*60}")

        # Run batch (checkpoint auto-resumes, so already-done instances are skipped)
        exit_code = run_batch(
            domain=args.domain,
            max_instances=cumulative_max,
            output_dir=args.output_dir,
            execution_mode=args.execution_mode,
            parallel=args.parallel,
            workers=args.workers,
        )

        # Count failures
        total, success, failed = count_failures(checkpoint_file)
        rate = (success / total * 100) if total > 0 else 0

        if exit_code != 0:
            print(f"⚠️  run_planbench_full.py exited with code {exit_code}")
            # If subprocess crashed AND no new instances processed → abort
            if total == total_prev:
                print(f"❌ Subprocess failed with no progress. Aborting.")
                break

        print(f"\n📊 Round {round_num} Stats:")
        print(f"   Total evaluated: {total}")
        print(f"   Success: {success} ({rate:.1f}%)")
        print(f"   Failed: {failed}")
        print(f"   Threshold: {args.failure_threshold}")

        if failed >= args.failure_threshold:
            print(f"\n✅ Threshold reached! {failed} failures ≥ {args.failure_threshold}")
            failed_list = extract_failed_instances(checkpoint_file, failed_file)
            print(f"   {len(failed_list)} failed instances saved to: {failed_file}")
            print(f"\n🔧 Ready for analysis → PRD → Ralph fix → review → re-run")
            return

        # Check if no new instances were processed (exhausted all available)
        if total == total_prev:
            print(f"\n⚠️  No new instances evaluated — all instances may be exhausted")
            break
        total_prev = total

        # Calculate next batch size: gap * 2
        gap = args.failure_threshold - failed
        next_batch = gap * 2
        cumulative_max = total + next_batch

        print(f"\n📈 Gap: {gap} failures needed")
        print(f"   Next batch: {next_batch} more instances")
        print(f"   Cumulative target: {cumulative_max}")

    # Exhausted rounds or instances
    total, success, failed = count_failures(checkpoint_file)
    print(f"\n{'='*60}")
    print(f"  ADAPTIVE BENCHMARK COMPLETE")
    print(f"  Total: {total} | Success: {success} | Failed: {failed}")
    print(f"  Threshold {args.failure_threshold} {'MET' if failed >= args.failure_threshold else 'NOT MET'}")
    print(f"{'='*60}")

    if failed > 0:
        failed_list = extract_failed_instances(checkpoint_file, failed_file)
        print(f"   {len(failed_list)} failed instances saved to: {failed_file}")


if __name__ == "__main__":
    main()
