#!/usr/bin/env python3
"""Compute TravelPlanner paper-style metrics (Table 3 format) from result JSON files.

Computes:
  - Delivery Rate
  - Commonsense Pass Rate (Micro / Macro)
  - Hard Constraint Pass Rate (Micro / Macro)
  - Final Pass Rate

Micro = total passed constraints / total constraints across all samples
Macro = samples where ALL constraints pass / total samples

Usage:
  python scripts/evaluation/compute_travelplanner_metrics.py \
    --results_dir runs/travelplanner_full_20260307_230607 \
    [--split test] [--modes baseline bdi bdi-repair]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# Official TravelPlanner total constraint counts per split
# commonsense: 8 constraints per sample
# hard: varies (budget always present, others conditional on query)
COMMONSENSE_KEYS = [
    'is_valid_information_in_current_city',
    'is_valid_information_in_sandbox',
    'is_reasonable_visiting_city',
    'is_valid_restaurants',
    'is_valid_transportation',
    'is_valid_attractions',
    'is_valid_accommodation',
    'is_not_absent',
]

HARD_KEYS = [
    'valid_cost',
    'valid_room_rule',
    'valid_cuisine',
    'valid_room_type',
    'valid_transportation',
]

# Official denominators from eval.py (these are the TOTALS across all samples)
OFFICIAL_DENOMINATORS = {
    'train':      {'commonsense': 360,  'hard': 105,  'samples': 45},
    'validation': {'commonsense': 1440, 'hard': 420,  'samples': 180},
    'test':       {'commonsense': 8000, 'hard': 2290, 'samples': 1000},
}


def compute_metrics(results: list[dict], split: str) -> dict:
    """Compute paper-style metrics from a list of per-sample result dicts."""
    total = len(results)
    if total == 0:
        return {}

    delivery_cnt = 0
    commonsense_pass_cnt = 0  # per-constraint pass count (for micro)
    commonsense_total_cnt = 0  # per-constraint total count (for micro)
    commonsense_macro_cnt = 0  # samples where ALL commonsense pass
    hard_pass_cnt = 0
    hard_total_cnt = 0
    hard_macro_cnt = 0
    final_cnt = 0

    for r in results:
        m = r.get('metrics', {})

        # Delivery
        if m.get('delivery', False):
            delivery_cnt += 1

        # Commonsense details
        cd = m.get('commonsense_details')
        if cd:
            all_pass = True
            for key in COMMONSENSE_KEYS:
                if key in cd:
                    val = cd[key]
                    passed = val[0] if isinstance(val, (list, tuple)) else val
                    if passed is None:
                        continue  # skip None (not applicable)
                    commonsense_total_cnt += 1
                    if passed:
                        commonsense_pass_cnt += 1
                    else:
                        all_pass = False
                else:
                    commonsense_total_cnt += 1
                    all_pass = False
            if all_pass:
                commonsense_macro_cnt += 1

        # Hard constraint details
        hd = m.get('hard_constraint_details')
        if hd:
            all_hard_pass = True
            for key in HARD_KEYS:
                if key in hd:
                    val = hd[key]
                    passed = val[0] if isinstance(val, (list, tuple)) else val
                    if passed is None:
                        continue  # skip None (not applicable for this query)
                    hard_total_cnt += 1
                    if passed:
                        hard_pass_cnt += 1
                    else:
                        all_hard_pass = False
            if all_hard_pass:
                hard_macro_cnt += 1

        # Final pass
        if m.get('final_pass', False):
            final_cnt += 1

    # Use official denominators if available and sample count matches
    denom = OFFICIAL_DENOMINATORS.get(split)
    if denom and total == denom['samples']:
        cs_micro_denom = denom['commonsense']
        hd_micro_denom = denom['hard']
    else:
        # Fallback: use actual counts
        cs_micro_denom = commonsense_total_cnt if commonsense_total_cnt > 0 else 1
        hd_micro_denom = hard_total_cnt if hard_total_cnt > 0 else 1

    return {
        'total': total,
        'delivery_rate': delivery_cnt / total * 100,
        'commonsense_micro': commonsense_pass_cnt / cs_micro_denom * 100,
        'commonsense_macro': commonsense_macro_cnt / total * 100,
        'hard_micro': hard_pass_cnt / hd_micro_denom * 100,
        'hard_macro': hard_macro_cnt / total * 100,
        'final_pass_rate': final_cnt / total * 100,
        # Raw counts for debugging
        '_cs_pass': commonsense_pass_cnt,
        '_cs_total': commonsense_total_cnt,
        '_cs_official_denom': cs_micro_denom,
        '_hd_pass': hard_pass_cnt,
        '_hd_total': hard_total_cnt,
        '_hd_official_denom': hd_micro_denom,
    }


def find_results_files(results_dir: Path, split: str, modes: list[str]) -> dict[str, Path]:
    """Find result JSON files for given split and modes."""
    found = {}
    for mode in modes:
        mode_dir = results_dir / split / mode
        if not mode_dir.exists():
            continue
        jsons = sorted(mode_dir.glob('results_travelplanner_*.json'))
        if jsons:
            found[mode] = jsons[-1]  # latest
    return found


def format_table(all_metrics: dict[str, dict], split: str) -> str:
    """Format metrics as a paper-style table."""
    total_samples = OFFICIAL_DENOMINATORS.get(split, {}).get('samples', '?')
    lines = []
    lines.append(f'TravelPlanner {split.capitalize()} Set (#{total_samples})')
    lines.append('=' * 90)
    header = f'{"Method":<25} {"Delivery":>8} {"CS-Micro":>9} {"CS-Macro":>9} {"HC-Micro":>9} {"HC-Macro":>9} {"Final":>8}'
    lines.append(header)
    lines.append('-' * 90)

    for mode, m in all_metrics.items():
        line = (
            f'{mode:<25} '
            f'{m["delivery_rate"]:>7.1f}% '
            f'{m["commonsense_micro"]:>8.1f}% '
            f'{m["commonsense_macro"]:>8.1f}% '
            f'{m["hard_micro"]:>8.1f}% '
            f'{m["hard_macro"]:>8.1f}% '
            f'{m["final_pass_rate"]:>7.1f}%'
        )
        lines.append(line)

    lines.append('=' * 90)
    return '\n'.join(lines)


def format_latex(all_metrics: dict[str, dict], split: str) -> str:
    """Format as LaTeX table row."""
    total_samples = OFFICIAL_DENOMINATORS.get(split, {}).get('samples', '?')
    lines = []
    lines.append(f'% {split.capitalize()} (#{total_samples})')
    for mode, m in all_metrics.items():
        row = (
            f'  {mode} & '
            f'{m["delivery_rate"]:.1f} & '
            f'{m["commonsense_micro"]:.1f} & '
            f'{m["commonsense_macro"]:.1f} & '
            f'{m["hard_micro"]:.1f} & '
            f'{m["hard_macro"]:.1f} & '
            f'{m["final_pass_rate"]:.1f} \\\\\\\\'
        )
        lines.append(row)
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Compute TravelPlanner paper metrics')
    parser.add_argument('--results_dir', type=Path, required=True,
                        help='Directory containing split/mode subdirs with results JSON')
    parser.add_argument('--split', type=str, default='test',
                        help='Split name (train/validation/test)')
    parser.add_argument('--modes', nargs='+', default=['baseline', 'bdi', 'bdi-repair'],
                        help='Modes to evaluate')
    parser.add_argument('--latex', action='store_true', help='Also output LaTeX rows')
    args = parser.parse_args()

    files = find_results_files(args.results_dir, args.split, args.modes)
    if not files:
        print(f'No results found in {args.results_dir / args.split}')
        return

    all_metrics = {}
    for mode, path in files.items():
        with open(path) as f:
            data = json.load(f)
        results = data.get('results', [])
        metrics = compute_metrics(results, args.split)
        all_metrics[mode] = metrics
        print(f'[{mode}] Loaded {len(results)} results from {path.name}')

    print()
    print(format_table(all_metrics, args.split))

    if args.latex:
        print()
        print(format_latex(all_metrics, args.split))


if __name__ == '__main__':
    main()
