#!/usr/bin/env python3
"""Submit TravelPlanner plans to the HuggingFace leaderboard via Gradio API."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from gradio_client import Client, handle_file


BASE = Path(__file__).resolve().parent.parent.parent


def log_factory(log_path: Path):
    def log(msg: str) -> None:
        line = f'[{time.strftime("%H:%M:%S")}] {msg}'
        print(line, flush=True)
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    return log


def connect_with_retry(log, hf_token: str, max_retries: int = 5):
    for attempt in range(max_retries):
        try:
            log(f'Connecting (attempt {attempt + 1}/{max_retries})...')
            client = Client('osunlp/TravelPlannerLeaderboard', hf_token=hf_token)
            log('Connected.')
            return client
        except Exception as exc:
            wait = 30 * (attempt + 1)
            log(f'Connection failed: {exc}. Waiting {wait}s...')
            time.sleep(wait)
    raise RuntimeError('Failed to connect after all retries')


def submit_one(client, log, mode: str, fpath: str, timeout_seconds: int, poll_seconds: int):
    log(f'{mode}: submitting {fpath}...')
    job = client.submit('test', 'sole-planning', handle_file(fpath), api_name='/add_new_eval')
    log(f'{mode}: job submitted, polling (max {timeout_seconds // 60} min)...')

    max_polls = max(1, timeout_seconds // poll_seconds)
    for i in range(max_polls):
        time.sleep(poll_seconds)
        status = job.status()
        if i % max(1, 60 // poll_seconds) == 0:
            log(f'{mode}: poll #{i + 1}, status={status.code}')
        if job.done():
            try:
                result = job.result(timeout=10)
                log(f'{mode}: SUCCESS!')
                log(f'{mode}: markdown={str(result[0])[:800]}')
                log(f'{mode}: report={result[1]}')
                return {'markdown': str(result[0]), 'report': str(result[1])}
            except Exception as exc:
                log(f'{mode}: result error: {exc}')
                return {'error': str(exc)}

    log(f'{mode}: TIMEOUT after {timeout_seconds}s')
    job.cancel()
    return {'error': 'timeout'}


def main() -> None:
    parser = argparse.ArgumentParser(description='Submit TravelPlanner sole-planning files to the leaderboard')
    parser.add_argument('--submit-dir', type=Path, default=BASE / 'runs' / 'tp_test_submit')
    parser.add_argument('--timeout-seconds', type=int, default=10800)
    parser.add_argument('--poll-seconds', type=int, default=10)
    parser.add_argument('--hf-token-env', default='HF_TOKEN')
    args = parser.parse_args()

    hf_token = os.environ.get(args.hf_token_env) or os.environ.get('HUGGINGFACE_TOKEN')
    if not hf_token:
        raise SystemExit(
            f'Missing HuggingFace token. Set {args.hf_token_env} or HUGGINGFACE_TOKEN.'
        )

    submit_dir = args.submit_dir.resolve()
    submit_dir.mkdir(parents=True, exist_ok=True)
    log_path = submit_dir / 'leaderboard_submit.log'
    log_path.write_text('', encoding='utf-8')
    log = log_factory(log_path)

    client = connect_with_retry(log, hf_token)

    files = [
        ('baseline', str(submit_dir / 'test_soleplanning_baseline.jsonl')),
        ('bdi', str(submit_dir / 'test_soleplanning_bdi.jsonl')),
        ('bdi-repair', str(submit_dir / 'test_soleplanning_bdi-repair.jsonl')),
    ]

    results = {}
    for mode, fpath in files:
        results[mode] = submit_one(
            client,
            log,
            mode,
            fpath,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
        log(f'{mode}: waiting 10s before next submission...')
        time.sleep(10)

    out = submit_dir / 'leaderboard_results.json'
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    log(f'ALL DONE. Results saved to {out}')


if __name__ == '__main__':
    main()
