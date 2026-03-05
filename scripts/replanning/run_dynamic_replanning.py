#!/usr/bin/env python3
"""
Dynamic Replanning (Repair) Evaluation
=======================================

Evaluates the PNSV Dynamic Replanning system.
Flow: 
1. Initial LLM plan generation (batch-optimized model by default)
2. Stepwise execution using VAL
3. On failure, DynamicReplanner generates a recovery plan (using caching model)
4. Repeat until success or max restarts.

Usage:
    python scripts/run_dynamic_replanning.py --domain blocksworld --max_instances 10

Author: BDI-LLM Research
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import argparse

from bdi_llm.planner import BDIPlanner
from bdi_llm.config import Config
from bdi_llm.schemas import BDIPlan
from bdi_llm.dynamic_replanner.executor import PlanExecutor, ExecutionResult
from bdi_llm.dynamic_replanner.replanner import DynamicReplanner

# Reuse PDDL parsing and NL conversion from planbench_utils
from scripts.evaluation.planbench_utils import (
    parse_pddl_problem,
    pddl_to_natural_language,
    resolve_domain_file,
    bdi_to_pddl_actions,
    find_all_instances,
)

# Background-safe progress: unified tqdm compat from planbench_utils
from scripts.evaluation.planbench_utils.tqdm_compat import tqdm

def generate_and_replan(
    beliefs: str,
    desire: str,
    pddl_problem_path: str,
    pddl_domain_path: str,
    domain: str = "blocksworld",
    max_replans: int = 3,
) -> dict:
    """
    Generate initial plan and dynamically replan upon failure.
    """
    result = {
        'initial_generation': {'success': False, 'time': 0},
        'initial_execution': {'success': False, 'failed_action': None},
        'replanning_rounds': 0,
        'replanning_history': [],
        'final_success': False,
        'total_time': 0,
    }

    start_eval_time = time.time()
    
    # 1. Initial Plan Generation
    planner = BDIPlanner(auto_repair=False, domain=domain)
    gen_start = time.time()
    try:
        gen_result = planner.generate_plan(beliefs=beliefs, desire=desire)
        initial_plan = gen_result.plan
        result['initial_generation']['success'] = True
    except Exception as e:
        result['initial_generation']['error'] = str(e)
        result['total_time'] = time.time() - start_eval_time
        return result
        
    result['initial_generation']['time'] = time.time() - gen_start
    pddl_actions = bdi_to_pddl_actions(initial_plan, domain=domain)
    
    # 2. Plan Executor
    executor = PlanExecutor(domain_file=pddl_domain_path, problem_file=pddl_problem_path)
    exec_res = executor.execute(pddl_actions)
    
    result['initial_execution']['success'] = exec_res.success
    result['initial_execution']['failed_action'] = exec_res.failed_action
    
    if exec_res.success:
        result['final_success'] = True
        result['total_time'] = time.time() - start_eval_time
        return result
        
    # 3. Dynamic Replanning Loop
    replanner = DynamicReplanner()  # Uses Config.LLM_MODEL by default
    current_exec_res = exec_res
    
    for i in range(max_replans):
        round_info = {
            'round': i + 1,
            'failed_at': current_exec_res.failed_action,
            'success': False,
            'time': 0
        }
        
        replan_start = time.time()
        recovery_plan = replanner.generate_recovery_plan(beliefs, desire, current_exec_res)
        round_info['time'] = time.time() - replan_start
        
        if not recovery_plan:
            round_info['error'] = "Replanner failed to generate a valid plan structure."
            result['replanning_history'].append(round_info)
            break
            
        recovery_actions = bdi_to_pddl_actions(recovery_plan, domain=domain)
        
        # Combine successful prefix with recovery plan
        total_plan = current_exec_res.executed_actions + recovery_actions
        current_exec_res = executor.execute(total_plan)
        
        round_info['success'] = current_exec_res.success
        result['replanning_history'].append(round_info)
        result['replanning_rounds'] += 1
        
        if current_exec_res.success:
            result['final_success'] = True
            break

    result['total_time'] = time.time() - start_eval_time
    return result

def run_dynamic_replanning_eval(
    domain: str,
    max_instances: Optional[int] = None,
    output_dir: str = "runs/dynamic_replanning",
    workers: int = 1,
    resume: bool = False,
):
    os.makedirs(output_dir, exist_ok=True)
    base_path = str(Path(__file__).parents[1] / "planbench_data" / "plan-bench")
    all_instances = find_all_instances(base_path, domain=domain)
    if max_instances:
        all_instances = all_instances[:max_instances]

    checkpoint_file = f"{output_dir}/checkpoint_{domain}.json"
    checkpoint_lock = Lock()

    # --- Resume from checkpoint ---
    results: list = []
    done_instances: set = set()
    if resume and os.path.exists(checkpoint_file):
        with open(checkpoint_file, 'r') as f:
            checkpoint_data = json.load(f)
        # Support both list and {results: [...]} formats
        if isinstance(checkpoint_data, list):
            results = checkpoint_data
        elif isinstance(checkpoint_data, dict):
            results = checkpoint_data.get('results', [])
        done_instances = {r.get('instance_file') or r.get('instance_name', '') for r in results}
        print(f"Resumed from checkpoint: {len(results)} instances already done.")

    pending = [inst for inst in all_instances if inst not in done_instances]

    print(f"\nEvaluating PNSV Dynamic Replanning")
    print(f"Domain: {domain}")
    print(f"Total instances: {len(all_instances)}  |  Pending: {len(pending)}  |  Resumed: {len(results)}")
    
    def _process_instance(inst_file: str):
        inst_name = Path(inst_file).stem
        try:
            pddl_data = parse_pddl_problem(inst_file)
            beliefs, desire = pddl_to_natural_language(pddl_data, domain)
            domain_name = pddl_data.get('domain_name', domain)
            domain_file = resolve_domain_file(domain_name)
            
            res = generate_and_replan(
                beliefs=beliefs,
                desire=desire,
                pddl_problem_path=inst_file,
                pddl_domain_path=domain_file,
                domain=domain,
                max_replans=3
            )
            
            init_ok = "✓" if res['initial_execution']['success'] else "✗"
            final_ok = "✓" if res['final_success'] else "✗"
            rounds = res['replanning_rounds']
            tqdm.write(f"  {inst_name}: Init={init_ok} | Replans={rounds} | Final={final_ok}")
            
            return {
                'instance_file': inst_file,
                'instance_name': inst_name,
                **res
            }
        except Exception as e:
            tqdm.write(f"  {inst_name}: ERROR - {e}")
            return {
                'instance_file': inst_file,
                'instance_name': inst_name,
                'error': str(e)
            }
            
    # Atomic checkpoint save
    def _save_checkpoint():
        tmp = f"{checkpoint_file}.tmp"
        with open(tmp, 'w') as f:
            json.dump({'domain': domain, 'results': results}, f, default=str)
        os.replace(tmp, checkpoint_file)

    # Always serial or parallel based on workers
    effective_workers = min(workers, max(len(pending), 1))
    pbar = tqdm(total=len(pending), desc=f"Replanning {domain}")
    
    if effective_workers <= 1:
        for inst in pending:
            results.append(_process_instance(inst))
            pbar.update(1)
            _save_checkpoint()
    else:
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            futures = [executor.submit(_process_instance, inst) for inst in pending]
            for future in as_completed(futures):
                with checkpoint_lock:
                    results.append(future.result())
                    _save_checkpoint()
                pbar.update(1)
    
    pbar.close()
    
    # Analyze
    total = len(results)
    if total == 0:
        print("\nNo instances processed. Nothing to report.")
        return
    init_success = sum(1 for r in results if r.get('initial_execution', {}).get('success', False))
    final_success = sum(1 for r in results if r.get('final_success', False))
    replan_success = final_success - init_success
    
    print("\n" + "="*50)
    print("RESULTS: Dynamic Replanning")
    print("="*50)
    print(f"Total Instances: {total}")
    print(f"Initial Zero-Shot Accuracy: {init_success} ({init_success/total:.1%})")
    print(f"Final Accuracy (+Replanning): {final_success} ({final_success/total:.1%})")
    print(f"Replanning Lift (Absolute): +{replan_success} instances")
    
    if (total - init_success) > 0:
        repair_rate = replan_success / (total - init_success)
        print(f"Repair Success Rate (Repaired / Failed): {repair_rate:.1%}")
        
    out_file = f"{output_dir}/results_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(out_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
        
    print(f"Saved to: {out_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dynamic Replanning Evaluation")
    parser.add_argument("--domain", type=str, required=True, choices=["blocksworld", "logistics", "depots"])
    parser.add_argument("--max_instances", type=int, default=None)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--output_dir", type=str, default="runs/dynamic_replanning")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from existing checkpoint file")
    args = parser.parse_args()

    run_dynamic_replanning_eval(
        domain=args.domain,
        max_instances=args.max_instances,
        workers=args.workers,
        output_dir=args.output_dir,
        resume=args.resume,
    )
