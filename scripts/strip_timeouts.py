#!/usr/bin/env python3
"""
Strip Timeout/Rate-Limit Failures from Checkpoints
===================================================

Removes API error failures (504/429) from checkpoint files to allow
benchmark resume without counting transient API errors as failures.

Usage:
    python scripts/strip_timeouts.py
"""

import json
import os
from pathlib import Path

PROJ = Path(__file__).parent.parent
RUNS = ['benchmark_gpt5_full', 'ablation_NAIVE', 'ablation_BDI_ONLY']
DOMAINS = ['blocksworld', 'logistics', 'depots']

API_ERROR_PATTERNS = ['504', '503', '429', 'Timeout', 'Gateway', 'rate limit', 'RateLimited']


def is_api_error(result):
    """Check if a result failure is due to API error rather than verification failure."""
    bdi = result.get('bdi_metrics', {})
    layers = bdi.get('verification_layers', {})
    errors = []

    # Collect all errors from all layers
    for layer in layers.values():
        errors.extend(layer.get('errors', []))

    # Also check top-level errors
    errors.extend(bdi.get('errors', []))

    # Check if any error matches API error patterns
    return any(
        any(p.lower() in str(e).lower() for e in errors)
        for p in API_ERROR_PATTERNS
    )


def main():
    print("=" * 60)
    print("STRIP TIMEOUT/RATE-LIMIT FAILURES FROM CHECKPOINTS")
    print("=" * 60)
    print()

    total_removed = 0

    for run in RUNS:
        for domain in DOMAINS:
            ckpt = PROJ / 'runs' / run / f'checkpoint_{domain}.json'
            if not ckpt.exists():
                print(f"SKIP: {ckpt} (not found)")
                continue

            with open(ckpt) as f:
                data = json.load(f)

            before = len(data['results'])
            # Keep results that either succeeded or failed due to API errors (to be retried)
            # Actually, we want to remove API error failures so they get re-run
            data['results'] = [
                r for r in data['results']
                if r.get('success') or not is_api_error(r)
            ]
            after = len(data['results'])

            removed = before - after
            total_removed += removed

            if removed > 0:
                with open(ckpt, 'w') as f:
                    json.dump(data, f, indent=2)
                print(f"{run}/{domain}: removed {removed} API error failures "
                      f"({before} -> {after})")
            else:
                print(f"{run}/{domain}: no API error failures to remove")

    print()
    print("=" * 60)
    print(f"TOTAL REMOVED: {total_removed}")
    print("=" * 60)
    print()
    print("Next step: Re-run benchmark with --workers 30 to retry removed instances")


if __name__ == "__main__":
    main()
