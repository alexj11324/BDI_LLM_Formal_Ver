#!/usr/bin/env python3
"""Run the TravelPlanner release matrix for validation and optional test submission."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import deque
from datetime import datetime
from pathlib import Path
from threading import Thread

PROJECT_ROOT = Path(__file__).resolve().parents[2]


VALIDATION_MODES = ("baseline", "bdi", "bdi-repair")


def _stream_pipe(pipe, target, tail: deque[str]) -> None:
    try:
        for line in iter(pipe.readline, ""):
            target.write(line)
            target.flush()
            tail.append(line)
    finally:
        pipe.close()


def run_command(cmd: list[str], *, env: dict[str, str], timeout_seconds: int) -> dict:
    started_at = datetime.now().isoformat()
    run_env = env.copy()
    run_env["PYTHONUNBUFFERED"] = "1"
    stdout_tail: deque[str] = deque(maxlen=200)
    stderr_tail: deque[str] = deque(maxlen=200)
    proc = subprocess.Popen(
        cmd,
        cwd=PROJECT_ROOT,
        env=run_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    stdout_thread = Thread(target=_stream_pipe, args=(proc.stdout, sys.stdout, stdout_tail), daemon=True)
    stderr_thread = Thread(target=_stream_pipe, args=(proc.stderr, sys.stderr, stderr_tail), daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    try:
        returncode = proc.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout_thread.join()
        stderr_thread.join()
        raise
    stdout_thread.join()
    stderr_thread.join()
    return {
        "command": cmd,
        "returncode": returncode,
        "stdout_tail": "".join(stdout_tail)[-4000:],
        "stderr_tail": "".join(stderr_tail)[-4000:],
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TravelPlanner validation/test release matrix")
    parser.add_argument("--run-validation", action="store_true")
    parser.add_argument("--run-test", action="store_true")
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--timeout-seconds", type=int, default=10800)
    parser.add_argument("--output-dir", type=Path, default=Path("runs/travelplanner_release_matrix"))
    parser.add_argument("--travelplanner-home", type=str, default=None)
    parser.add_argument("--hf-token-env", default="HF_TOKEN")
    args = parser.parse_args()

    if not args.run_validation and not args.run_test:
        raise SystemExit("Nothing to do. Pass --run-validation and/or --run-test.")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env.setdefault("TRAVELPLANNER_BDI_PROMPT_VERSION", "v3")

    summary: dict[str, object] = {
        "prompt_version": env["TRAVELPLANNER_BDI_PROMPT_VERSION"],
        "workers": args.workers,
        "timeout_seconds": args.timeout_seconds,
        "validation": {},
        "test_generation": {},
        "test_submission": None,
    }

    if args.run_validation:
        validation_dir = output_dir / "validation"
        for mode in VALIDATION_MODES:
            cmd = [
                sys.executable,
                "scripts/evaluation/run_travelplanner_eval.py",
                "--split",
                "validation",
                "--execution_mode",
                mode,
                "--workers",
                str(args.workers),
                "--output_dir",
                str(validation_dir),
            ]
            if args.travelplanner_home:
                cmd.extend(["--travelplanner_home", args.travelplanner_home])
            summary["validation"][mode] = run_command(cmd, env=env, timeout_seconds=args.timeout_seconds)

    if args.run_test:
        submit_dir = output_dir / "test_submit"
        for mode in ("baseline", "bdi", "bdi-repair"):
            cmd = [
                sys.executable,
                "scripts/evaluation/run_travelplanner_test_submit.py",
                "--mode",
                mode,
                "--output_dir",
                str(submit_dir),
                "--workers",
                str(args.workers),
            ]
            summary["test_generation"][mode] = run_command(cmd, env=env, timeout_seconds=args.timeout_seconds)

        submit_cmd = [
            sys.executable,
            "scripts/evaluation/submit_to_leaderboard.py",
            "--submit-dir",
            str(submit_dir),
            "--timeout-seconds",
            str(args.timeout_seconds),
            "--hf-token-env",
            args.hf_token_env,
        ]
        summary["test_submission"] = run_command(submit_cmd, env=env, timeout_seconds=args.timeout_seconds)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = output_dir / f"release_matrix_{stamp}.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"summary_path": str(summary_path), **summary}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
