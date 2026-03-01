#!/usr/bin/env python3
"""
Diagnostic Script: Verification Flow Debug
==========================================

Analyzes why FULL_VERIFIED underperforms NAIVE on Logistics.

Key questions:
1. Why is auto-repair not triggered? (465 failures → 1 trigger)
2. Why is VAL repair loop never entered? (0 attempts)
3. What specific structural errors cause false rejections?

Usage:
    python scripts/debug_verification_flow.py
"""

import json
import os
from pathlib import Path

PROJ = Path(__file__).parent.parent
FULL_VERIFIED_CKPT = PROJ / "runs/benchmark_gpt5_full/checkpoint_logistics.json"
NAIVE_CKPT = PROJ / "runs/ablation_NAIVE/checkpoint_logistics.json"
BDI_ONLY_CKPT = PROJ / "runs/ablation_BDI_ONLY/checkpoint_logistics.json"


def load_results(path):
    with open(path) as f:
        return json.load(f)


def analyze_verification_flow(results, mode_name):
    """Analyze verification flow for a single mode."""
    total = len(results)
    success = sum(1 for r in results if r.get('success'))

    # Categorize failures
    structural_failures = []
    symbolic_failures = []
    physics_failures = []

    auto_repair_triggered = []
    val_repair_attempted = []

    for i, r in enumerate(results):
        bdi = r.get('bdi_metrics', {})
        layers = bdi.get('verification_layers', {})

        if not layers.get('structural', {}).get('valid', True):
            structural_failures.append((i, r))
        if not layers.get('symbolic', {}).get('valid', True):
            symbolic_failures.append((i, r))
        if not layers.get('physics', {}).get('valid', True):
            physics_failures.append((i, r))

        if bdi.get('auto_repair', {}).get('triggered'):
            auto_repair_triggered.append((i, r))
        if bdi.get('val_repair', {}).get('attempts', 0) > 0:
            val_repair_attempted.append((i, r))

    print(f"\n{'='*60}")
    print(f"MODE: {mode_name}")
    print(f"{'='*60}")
    print(f"Total: {total} | Success: {success} ({100*success/total:.1f}%) | Failed: {total-success}")
    print()
    print("FAILURE BREAKDOWN:")
    print(f"  Structural failures: {len(structural_failures)} ({100*len(structural_failures)/total:.1f}%)")
    print(f"  Symbolic failures: {len(symbolic_failures)} ({100*len(symbolic_failures)/total:.1f}%)")
    print(f"  Physics failures: {len(physics_failures)} ({100*len(physics_failures)/total:.1f}%)")
    print()
    print("REPAIR STATISTICS:")
    print(f"  Auto-repair triggered: {len(auto_repair_triggered)}")
    print(f"  VAL repair attempted: {len(val_repair_attempted)}")
    print()

    # Analyze structural failure patterns
    if structural_failures:
        print("STRUCTURAL FAILURE PATTERNS (first 5):")
        for idx, r in structural_failures[:5]:
            bdi = r.get('bdi_metrics', {})
            layers = bdi.get('verification_layers', {})
            struct_errors = layers.get('structural', {}).get('errors', [])
            print(f"  [{idx}] {r['instance_name']}: {struct_errors[:2]}")
            print(f"      Auto-repair triggered: {bdi.get('auto_repair', {}).get('triggered')}")
        print()

    # Analyze cases where structural fails but auto-repair not triggered
    no_repair_cases = []
    for idx, r in structural_failures:
        bdi = r.get('bdi_metrics', {})
        if not bdi.get('auto_repair', {}).get('triggered'):
            no_repair_cases.append((idx, r))

    if no_repair_cases:
        print(f"CRITICAL: {len(no_repair_cases)} structural failures without auto-repair!")
        print("Sample cases (first 3):")
        for idx, r in no_repair_cases[:3]:
            bdi = r.get('bdi_metrics', {})
            layers = bdi.get('verification_layers', {})
            struct_errors = layers.get('structural', {}).get('errors', [])
            print(f"  [{idx}] {r['instance_name']}:")
            print(f"      Structural errors: {struct_errors[:2]}")
            print(f"      Auto-repair: triggered={bdi.get('auto_repair', {}).get('triggered')}")
        print()

    return {
        'total': total,
        'success': success,
        'structural_failures': structural_failures,
        'symbolic_failures': symbolic_failures,
        'physics_failures': physics_failures,
        'auto_repair_triggered': auto_repair_triggered,
        'val_repair_attempted': val_repair_attempted,
        'no_repair_structural_failures': no_repair_cases
    }


def compare_modes(fv_data, naive_data, bdi_only_data):
    """Compare verification flow across modes."""
    print("\n" + "="*60)
    print("CROSS-MODE COMPARISON")
    print("="*60)

    print("\nSUCCESS RATES:")
    print(f"  FULL_VERIFIED: {fv_data['success']}/{fv_data['total']} ({100*fv_data['success']/fv_data['total']:.1f}%)")
    print(f"  NAIVE: {naive_data['success']}/{naive_data['total']} ({100*naive_data['success']/naive_data['total']:.1f}%)")
    print(f"  BDI_ONLY: {bdi_only_data['success']}/{bdi_only_data['total']} ({100*bdi_only_data['success']/bdi_only_data['total']:.1f}%)")
    print()

    print("STRUCTURAL FAILURES:")
    print(f"  FULL_VERIFIED: {len(fv_data['structural_failures'])} ({100*len(fv_data['structural_failures'])/fv_data['total']:.1f}%)")
    print(f"  NAIVE: {len(naive_data['structural_failures'])} ({100*len(naive_data['structural_failures'])/naive_data['total']:.1f}%)")
    print(f"  BDI_ONLY: {len(bdi_only_data['structural_failures'])} ({100*len(bdi_only_data['structural_failures'])/bdi_only_data['total']:.1f}%)")
    print()

    print("AUTO-REPAIR TRIGGERED:")
    print(f"  FULL_VERIFIED: {len(fv_data['auto_repair_triggered'])} (rate: {100*len(fv_data['auto_repair_triggered'])/len(fv_data['structural_failures']) if fv_data['structural_failures'] else 0:.1f}%)")
    print(f"  NAIVE: {len(naive_data['auto_repair_triggered'])} (rate: {100*len(naive_data['auto_repair_triggered'])/len(naive_data['structural_failures']) if naive_data['structural_failures'] else 0:.1f}%)")
    print(f"  BDI_ONLY: {len(bdi_only_data['auto_repair_triggered'])} (rate: {100*len(bdi_only_data['auto_repair_triggered'])/len(bdi_only_data['structural_failures']) if bdi_only_data['structural_failures'] else 0:.1f}%)")
    print()

    print("VAL REPAIR ATTEMPTED:")
    print(f"  FULL_VERIFIED: {len(fv_data['val_repair_attempted'])}")
    print(f"  NAIVE: {len(naive_data['val_repair_attempted'])}")
    print(f"  BDI_ONLY: {len(bdi_only_data['val_repair_attempted'])}")
    print()

    # Find instances where NAIVE succeeded but FULL_VERIFIED failed
    naive_success_names = {r['instance_name'] for _, r in naive_data['success']} if isinstance(naive_data['success'], list) else set()

    # Re-compute success as list for this comparison
    with open(NAIVE_CKPT) as f:
        naive_raw = json.load(f)
    with open(FULL_VERIFIED_CKPT) as f:
        fv_raw = json.load(f)

    naive_success_names = {r['instance_name'] for r in naive_raw['results'] if r.get('success')}
    fv_failed_names = {r['instance_name'] for r in fv_raw['results'] if not r.get('success')}

    naive_success_but_fv_failed = naive_success_names & fv_failed_names

    print(f"INSTANCES WHERE NAIVE SUCCEEDED BUT FULL_VERIFIED FAILED: {len(naive_success_but_fv_failed)}")
    fv_failed_count = sum(1 for r in fv_raw['results'] if not r.get('success'))
    if fv_failed_count > 0:
        print(f"  This represents {100*len(naive_success_but_fv_failed)/fv_failed_count:.0f}% of FULL_VERIFIED's failures")
    print()

    # Sample specific failures
    print("SAMPLE FALSE REJECTIONS (first 5):")
    sample_count = 0
    for r in fv_raw['results']:
        if not r.get('success') and r['instance_name'] in naive_success_names and sample_count < 5:
            bdi = r.get('bdi_metrics', {})
            layers = bdi.get('verification_layers', {})
            print(f"  {r['instance_name']}:")
            print(f"    Structural: {layers.get('structural', {}).get('valid')} - {layers.get('structural', {}).get('errors', [])[:2]}")
            print(f"    Auto-repair: {bdi.get('auto_repair', {}).get('triggered')}")
            print(f"    VAL repair: {bdi.get('val_repair', {}).get('attempts', 0)} attempts")
            sample_count += 1
    print()


def main():
    print("="*60)
    print("VERIFICATION FLOW DIAGNOSTIC")
    print("="*60)

    # Load data
    print("\nLoading benchmark results...")
    fv_results = load_results(FULL_VERIFIED_CKPT)
    naive_results = load_results(NAIVE_CKPT)
    bdi_only_results = load_results(BDI_ONLY_CKPT)
    print(f"Loaded: FULL_VERIFIED ({len(fv_results['results'])}), NAIVE ({len(naive_results['results'])}), BDI_ONLY ({len(bdi_only_results['results'])})")

    # Analyze each mode
    fv_data = analyze_verification_flow(fv_results['results'], "FULL_VERIFIED")
    naive_data = analyze_verification_flow(naive_results['results'], "NAIVE")
    bdi_only_data = analyze_verification_flow(bdi_only_results['results'], "BDI_ONLY")

    # Compare modes
    compare_modes(fv_data, naive_data, bdi_only_data)

    # Recommendations
    print("="*60)
    print("DIAGNOSTIC RECOMMENDATIONS")
    print("="*60)
    print("""
Based on this analysis, the following issues are confirmed:

1. AUTO-REPAIR NOT TRIGGERED
   - {0} structural failures without auto-repair in FULL_VERIFIED
   - This suggests bug in trigger condition at planner.py:1132

2. VAL REPAIR LOOP BLOCKED
   - Structural failure (struct_valid=False) prevents entering VAL repair loop
   - See run_planbench_full.py:1206: "if struct_valid and ..."

3. FALSE REJECTIONS BY STRUCTURAL VERIFIER
   - {1} instances where NAIVE succeeded but FULL_VERIFIED failed
   - Structural verifier may be too strict or buggy

RECOMMENDED FIXES:
1. Add debug logging to auto-repair trigger (planner.py:1132-1143)
2. Decouple structural repair from VAL repair (run_planbench_full.py:1201-1290)
3. Investigate structural verifier for false positives (verifier.py)
""".format(
        len(fv_data['no_repair_structural_failures']),
        len(set(r['instance_name'] for _, r in fv_data['structural_failures']) &
            set(r['instance_name'] for r in naive_results['results'] if r.get('success')))
    ))


if __name__ == "__main__":
    main()
