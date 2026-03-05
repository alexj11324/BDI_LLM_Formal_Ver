#!/usr/bin/env python3
"""
Verification-Only PlanBench Evaluation
=======================================

Evaluates the PNSV verification framework WITHOUT repair.
Flow: LLM generates plan → Structural verification → VAL verification → Record results

This script is DECOUPLED from the full pipeline (run_planbench_full.py).
It reuses PDDL parsing and NL conversion utilities but has its own
clean evaluation loop focused purely on verification metrics.

Usage:
    # Run on blocksworld (10 instances for testing)
    python scripts/run_verification_only.py --domain blocksworld --max_instances 10

    # Full evaluation across all domains
    python scripts/run_verification_only.py --domain blocksworld
    python scripts/run_verification_only.py --domain logistics
    python scripts/run_verification_only.py --domain depots

Author: BDI-LLM Research
"""

import sys
import os
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import argparse

# Background-safe progress: use tqdm only when stdout is a tty
IS_TTY = sys.stdout.isatty()
if IS_TTY:
    from tqdm import tqdm
else:
    # Dummy tqdm for nohup/background execution
    class tqdm:
        def __init__(self, iterable=None, total=None, desc="", **kwargs):
            self.iterable = iterable
            self.total = total or (len(iterable) if iterable else 0)
            self.desc = desc
            self.n = 0
            if self.total:
                print(f"{desc}: 0/{self.total}")
        def __iter__(self):
            for item in self.iterable:
                yield item
                self.n += 1
                if self.n % 10 == 0 or self.n == self.total:
                    print(f"{self.desc}: {self.n}/{self.total}")
        def update(self, n=1):
            self.n += n
            if self.n % 10 == 0 or self.n == self.total:
                print(f"{self.desc}: {self.n}/{self.total}")
        def close(self): pass
        @staticmethod
        def write(s): print(s)

# Setup path
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.bdi_llm.planner import BDIPlanner
from src.bdi_llm.config import Config
from src.bdi_llm.schemas import BDIPlan
from src.bdi_llm.verifier import PlanVerifier

# Reuse PDDL parsing and NL conversion from existing script
from scripts.run_planbench_full import (
    parse_pddl_problem,
    pddl_to_natural_language,
    resolve_domain_file,
    bdi_to_pddl_actions,
    find_all_instances,
)


# ============================================================================
# CORE: GENERATE + VERIFY (NO REPAIR)
# ============================================================================

def generate_and_verify(
    beliefs: str,
    desire: str,
    pddl_problem_path: str,
    pddl_domain_path: str,
    domain: str = "blocksworld",
    max_retries: int = 3,
) -> dict:
    """
    Generate a plan and verify it. No repair.

    Returns a result dict with:
    - generation: success, time, num_nodes, num_edges
    - structural: valid, errors
    - symbolic: valid, errors (VAL result = ground truth)
    - agreement: whether structural and VAL agree
    """
    from src.bdi_llm.symbolic_verifier import PDDLSymbolicVerifier

    result = {
        'generation': {
            'success': False,
            'time': 0,
            'num_nodes': 0,
            'num_edges': 0,
            'error': None,
        },
        'structural': {
            'valid': False,
            'errors': [],
            'hard_errors': [],
            'warnings': [],
        },
        'symbolic': {
            'valid': False,
            'errors': [],
            'ran': False,
        },
        'agreement': None,  # True if structural and symbolic agree
    }

    # Step 1: Generate plan
    start_time = time.time()
    plan = None
    for attempt in range(max_retries):
        try:
            planner = BDIPlanner(auto_repair=False, domain=domain)
            gen_result = planner.generate_plan(beliefs=beliefs, desire=desire)
            plan = gen_result.plan
            result['generation']['success'] = True
            result['generation']['time'] = time.time() - start_time
            result['generation']['num_nodes'] = len(plan.nodes)
            result['generation']['num_edges'] = len(plan.edges)
            break
        except Exception as e:
            error_str = str(e).lower()
            if any(kw in error_str for kw in ['connection', 'timeout', 'rate', '429', 'quota']):
                if attempt < max_retries - 1:
                    wait_time = 2 ** (attempt + 1)
                    print(f"    API error, retrying in {wait_time}s... ({attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
            result['generation']['error'] = str(e)[:300]
            result['generation']['time'] = time.time() - start_time
            return result

    if plan is None:
        return result

    # Step 2: Structural verification
    try:
        G = plan.to_networkx()
        struct_result = PlanVerifier.verify(G)
        result['structural']['valid'] = struct_result.is_valid
        result['structural']['errors'] = struct_result.errors
        result['structural']['hard_errors'] = struct_result.hard_errors
        result['structural']['warnings'] = struct_result.warnings
    except Exception as e:
        result['structural']['errors'] = [f"Structural verification error: {str(e)[:200]}"]

    # Step 3: Symbolic verification (VAL = ground truth)
    try:
        pddl_actions = bdi_to_pddl_actions(plan, domain=domain)
        val_verifier = PDDLSymbolicVerifier()
        symbolic_valid, symbolic_errors = val_verifier.verify_plan(
            domain_file=pddl_domain_path,
            problem_file=pddl_problem_path,
            plan_actions=pddl_actions,
            verbose=False,
        )
        result['symbolic']['valid'] = symbolic_valid
        result['symbolic']['errors'] = [
            e for e in symbolic_errors
            if not e.lstrip().startswith("Full VAL output:")
        ][:5]  # Keep only top 5 errors
        result['symbolic']['ran'] = True
    except Exception as e:
        result['symbolic']['errors'] = [f"VAL error: {str(e)[:200]}"]
        result['symbolic']['ran'] = True

    # Step 4: Agreement analysis
    if result['symbolic']['ran']:
        result['agreement'] = result['structural']['valid'] == result['symbolic']['valid']

    return result


# ============================================================================
# BATCH EVALUATION
# ============================================================================

def run_verification_eval(
    domain: str,
    max_instances: Optional[int] = None,
    output_dir: str = "runs/verification_results",
    workers: int = 1,
) -> dict:
    """
    Run verification-only evaluation on a domain.

    Returns summary dict with aggregate metrics.
    """
    print(f"\n{'='*70}")
    print(f"  VERIFICATION-ONLY EVALUATION: {domain}")
    print(f"  Model: {Config.MODEL_NAME}")
    print(f"{'='*70}\n")

    base_path = Path(__file__).resolve().parent.parent / "planbench_data/plan-bench"
    os.makedirs(output_dir, exist_ok=True)

    # Find instances
    instances = find_all_instances(base_path, domain)
    if max_instances:
        instances = instances[:max_instances]
    print(f"Found {len(instances)} instances\n")

    # Checkpoint support
    checkpoint_file = f"{output_dir}/checkpoint_verifyonly_{domain}.json"
    completed = {}
    if os.path.exists(checkpoint_file):
        with open(checkpoint_file, 'r') as f:
            checkpoint_data = json.load(f)
            completed = {r['instance_file']: r for r in checkpoint_data.get('results', [])}
        print(f"Resuming: skipping {len(completed)} completed instances\n")

    results = list(completed.values())
    pending = [inst for inst in instances if inst not in completed]
    checkpoint_lock = Lock()

    def _process_instance(inst_file: str) -> dict:
        """Process a single instance (thread-safe)."""
        inst_name = Path(inst_file).stem
        try:
            pddl_data = parse_pddl_problem(inst_file)
            beliefs, desire = pddl_to_natural_language(pddl_data, domain)
            domain_name = pddl_data.get('domain_name', domain)
            domain_file = resolve_domain_file(domain_name)

            verify_result = generate_and_verify(
                beliefs=beliefs,
                desire=desire,
                pddl_problem_path=inst_file,
                pddl_domain_path=domain_file,
                domain=domain,
            )

            gen_ok = "✓" if verify_result['generation']['success'] else "✗"
            struct_ok = "✓" if verify_result['structural']['valid'] else "✗"
            val_ok = "✓" if verify_result['symbolic']['valid'] else "✗"
            agree = "=" if verify_result['agreement'] else "≠"
            tqdm.write(f"  {inst_name}: gen={gen_ok} struct={struct_ok} VAL={val_ok} [{agree}]")

            return {
                'instance_file': inst_file,
                'instance_name': inst_name,
                'timestamp': datetime.now().isoformat(),
                **verify_result,
            }
        except Exception as e:
            tqdm.write(f"  {inst_name}: ERROR - {str(e)[:100]}")
            return {
                'instance_file': inst_file,
                'instance_name': inst_name,
                'timestamp': datetime.now().isoformat(),
                'generation': {'success': False, 'error': str(e)[:300]},
                'structural': {'valid': False},
                'symbolic': {'valid': False, 'ran': False},
                'agreement': None,
            }

    # Evaluate (parallel or serial)
    effective_workers = min(workers, len(pending)) if pending else 1
    print(f"Workers: {effective_workers}\n")

    if effective_workers <= 1:
        # Serial mode
        for inst_file in tqdm(pending, desc=f"Verifying {domain}"):
            result = _process_instance(inst_file)
            results.append(result)
            _save_checkpoint(results, checkpoint_file, domain)
    else:
        # Parallel mode
        pbar = tqdm(total=len(pending), desc=f"Verifying {domain}")
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            futures = {executor.submit(_process_instance, inst): inst for inst in pending}
            for future in as_completed(futures):
                result = future.result()
                with checkpoint_lock:
                    results.append(result)
                    _save_checkpoint(results, checkpoint_file, domain)
                pbar.update(1)
        pbar.close()

    # Final summary
    summary = _compute_summary(results, domain)
    _print_summary(summary)

    # Save final results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    result_file = f"{output_dir}/verify_{domain}_{timestamp}.json"
    with open(result_file, 'w') as f:
        json.dump({'summary': summary, 'results': results}, f, indent=2, default=str)
    print(f"\nResults saved to: {result_file}")

    return summary


def _save_checkpoint(results: list, checkpoint_file: str, domain: str):
    """Save checkpoint atomically."""
    tmp = f"{checkpoint_file}.tmp"
    with open(tmp, 'w') as f:
        json.dump({'domain': domain, 'results': results}, f, default=str)
    os.replace(tmp, checkpoint_file)


def _compute_summary(results: list, domain: str) -> dict:
    """Compute aggregate metrics from results."""
    total = len(results)
    gen_success = sum(1 for r in results if r.get('generation', {}).get('success', False))
    struct_valid = sum(1 for r in results if r.get('structural', {}).get('valid', False))
    val_valid = sum(1 for r in results if r.get('symbolic', {}).get('valid', False))
    val_ran = sum(1 for r in results if r.get('symbolic', {}).get('ran', False))

    # Agreement analysis (only where VAL ran)
    val_results = [r for r in results if r.get('symbolic', {}).get('ran', False)]
    agree = sum(1 for r in val_results if r.get('agreement', False))

    # Error detection analysis
    val_invalid = [r for r in val_results if not r.get('symbolic', {}).get('valid', False)]
    struct_caught = sum(1 for r in val_invalid if not r.get('structural', {}).get('valid', False))

    # False positive analysis
    val_valid_list = [r for r in val_results if r.get('symbolic', {}).get('valid', False)]
    struct_false_pos = sum(1 for r in val_valid_list if not r.get('structural', {}).get('valid', False))

    return {
        'domain': domain,
        'model': Config.MODEL_NAME,
        'total_instances': total,
        'generation_success': gen_success,
        'structural_valid': struct_valid,
        'val_valid': val_valid,
        'val_ran': val_ran,
        'agreement': agree,
        'agreement_rate': agree / val_ran if val_ran > 0 else 0,
        'llm_accuracy': val_valid / gen_success if gen_success > 0 else 0,
        'error_detection': {
            'val_invalid_total': len(val_invalid),
            'structural_caught': struct_caught,
            'structural_missed': len(val_invalid) - struct_caught,
            'detection_rate': struct_caught / len(val_invalid) if val_invalid else 1.0,
        },
        'false_positives': {
            'val_valid_total': len(val_valid_list),
            'struct_false_positives': struct_false_pos,
            'false_positive_rate': struct_false_pos / len(val_valid_list) if val_valid_list else 0,
        },
        'avg_generation_time': sum(
            r.get('generation', {}).get('time', 0) for r in results
        ) / total if total > 0 else 0,
    }


def _print_summary(summary: dict):
    """Print formatted summary."""
    print(f"\n{'='*70}")
    print(f"  RESULTS: {summary['domain']}")
    print(f"  Model: {summary['model']}")
    print(f"{'='*70}")

    print(f"\n--- LLM Performance ---")
    print(f"Generation success: {summary['generation_success']}/{summary['total_instances']}")
    print(f"LLM accuracy (VAL): {summary['val_valid']}/{summary['generation_success']} ({summary['llm_accuracy']:.1%})")

    print(f"\n--- Verification Agreement ---")
    print(f"Structural valid: {summary['structural_valid']}")
    print(f"VAL valid:        {summary['val_valid']}")
    print(f"Agreement:        {summary['agreement']}/{summary['val_ran']} ({summary['agreement_rate']:.1%})")

    ed = summary['error_detection']
    print(f"\n--- Error Detection (structural vs VAL) ---")
    print(f"VAL found errors:       {ed['val_invalid_total']}")
    print(f"Structural also caught: {ed['structural_caught']} ({ed['detection_rate']:.1%})")
    print(f"Structural missed:      {ed['structural_missed']}")

    fp = summary['false_positives']
    print(f"\n--- False Positives ---")
    print(f"VAL valid plans:        {fp['val_valid_total']}")
    print(f"Struct false positives: {fp['struct_false_positives']} ({fp['false_positive_rate']:.1%})")

    print(f"\nAvg generation time: {summary['avg_generation_time']:.1f}s")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Verification-only PlanBench evaluation")
    parser.add_argument("--domain", type=str, required=True,
                        choices=["blocksworld", "logistics", "depots"],
                        help="PlanBench domain")
    parser.add_argument("--max_instances", type=int, default=None,
                        help="Maximum instances to evaluate")
    parser.add_argument("--workers", type=int, default=1,
                        help="Number of parallel workers (default: 1)")
    parser.add_argument("--output_dir", type=str, default="runs/verification_results",
                        help="Output directory for results")
    args = parser.parse_args()

    run_verification_eval(
        domain=args.domain,
        max_instances=args.max_instances,
        output_dir=args.output_dir,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
