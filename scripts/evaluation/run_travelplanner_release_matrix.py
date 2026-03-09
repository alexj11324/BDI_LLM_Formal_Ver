#!/usr/bin/env python3
"""Run the TravelPlanner release matrix for validation and optional test submission."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime


PROJECT_ROOT = Path(__file__).resolve().parents[2]


VALIDATION_MODES = ('baseline', 'bdi', 'bdi-repair')


def run_command(cmd: list[str], *, env: dict[str, str], timeout_seconds: int) -> dict:
    started_at = datetime.now().isoformat()
    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        env=env,
        timeout=timeout_seconds,
        capture_output=True,
        text=True,
    )
    return {
        'command': cmd,
        'returncode': proc.returncode,
        'stdout_tail': proc.stdout[-4000:],
        'stderr_tail': proc.stderr[-4000:],
        'started_at': started_at,
        'finished_at': datetime.now().isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Run TravelPlanner validation/test release matrix')
    parser.add_argument('--run-validation', action='store_true')
    parser.add_argument('--run-test', action='store_true')
    parser.add_argument('--workers', type=int, default=20)
    parser.add_argument('--timeout-seconds', type=int, default=10800)
    parser.add_argument('--output-dir', type=Path, default=Path('runs/travelplanner_release_matrix'))
    parser.add_argument('--travelplanner-home', type=str, default=None)
    parser.add_argument('--hf-token-env', default='HF_TOKEN')
    args = parser.parse_args()

    if not args.run_validation and not args.run_test:
        raise SystemExit('Nothing to do. Pass --run-validation and/or --run-test.')

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env['TRAVELPLANNER_BDI_PROMPT_VERSION'] = 'v3'

    summary: dict[str, object] = {
        'prompt_version': env['TRAVELPLANNER_BDI_PROMPT_VERSION'],
        'workers': args.workers,
        'timeout_seconds': args.timeout_seconds,
        'validation': {},
        'test_generation': {},
        'test_submission': None,
    }

    if args.run_validation:
        validation_dir = output_dir / 'validation'
        for mode in VALIDATION_MODES:
            cmd = [
                sys.executable,
                'scripts/evaluation/run_travelplanner_eval.py',
                '--split', 'validation',
                '--execution_mode', mode,
                '--workers', str(args.workers),
                '--output_dir', str(validation_dir),
            ]
            if args.travelplanner_home:
                cmd.extend(['--travelplanner_home', args.travelplanner_home])
            summary['validation'][mode] = run_command(cmd, env=env, timeout_seconds=args.timeout_seconds)

    if args.run_test:
        submit_dir = output_dir / 'test_submit'
        for mode in ('baseline', 'bdi', 'bdi-repair'):
            cmd = [
                sys.executable,
                'scripts/evaluation/run_travelplanner_test_submit.py',
                '--mode', mode,
                '--output_dir', str(submit_dir),
                '--workers', str(args.workers),
            ]
            summary['test_generation'][mode] = run_command(cmd, env=env, timeout_seconds=args.timeout_seconds)

        submit_cmd = [
            sys.executable,
            'scripts/evaluation/submit_to_leaderboard.py',
            '--submit-dir', str(submit_dir),
            '--timeout-seconds', str(args.timeout_seconds),
            '--hf-token-env', args.hf_token_env,
        ]
        summary['test_submission'] = run_command(submit_cmd, env=env, timeout_seconds=args.timeout_seconds)

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    summary_path = output_dir / f'release_matrix_{stamp}.json'
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'summary_path': str(summary_path), **summary}, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
