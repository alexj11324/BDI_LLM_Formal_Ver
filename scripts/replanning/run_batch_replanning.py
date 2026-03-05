#!/usr/bin/env python3
"""
Batch Dynamic Replanning Evaluation
====================================

Uses DashScope Batch API for cost-effective parallel inference.

Flow:
  Round 1: Submit ALL initial plan generation requests as a batch (50% cost)
           → Wait → Download → Parse plans
  Local:   VAL step-by-step verification for each plan
           → Split into PASS / FAIL
  Round 2: Submit FAIL instances as recovery requests in a new batch
           → Wait → Download → Parse → Re-verify
  Round 3: Repeat for remaining failures (max 3 rounds)

Usage:
    python scripts/run_batch_replanning.py --domain logistics --max_instances 5
    python scripts/run_batch_replanning.py --domain logistics  # all instances

Author: BDI-LLM Research
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import argparse
import logging

from bdi_llm.schemas import BDIPlan
from bdi_llm.batch_engine import (
    BatchEngine,
    build_initial_plan_messages,
    build_replan_messages,
    parse_plan_from_text,
)
from bdi_llm.dynamic_replanner.executor import PlanExecutor

# Reuse PDDL utilities from planbench_utils
from scripts.evaluation.planbench_utils import (
    parse_pddl_problem,
    pddl_to_natural_language,
    resolve_domain_file,
    bdi_to_pddl_actions,
    find_all_instances,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Instance data container
# ------------------------------------------------------------------ #

class InstanceData:
    """Holds all data for a single PlanBench instance across rounds."""

    def __init__(self, inst_file: str, domain: str):
        self.inst_file = inst_file
        self.inst_name = Path(inst_file).stem
        self.domain = domain

        # Parse PDDL
        self.pddl_data = parse_pddl_problem(inst_file)
        self.beliefs, self.desire = pddl_to_natural_language(self.pddl_data, domain)
        domain_name = self.pddl_data.get("domain_name", domain)
        self.domain_file = resolve_domain_file(domain_name)

        # Results tracking
        self.plan: Optional[BDIPlan] = None
        self.initial_success: bool = False
        self.final_success: bool = False
        self.replanning_rounds: int = 0
        self.error: Optional[str] = None

        # For replanning: track execution state
        self.executed_actions: List[str] = []
        self.failed_action: Optional[str] = None
        self.failure_reasons: List[str] = []

    @property
    def custom_id(self) -> str:
        return f"{self.domain}_{self.inst_name}"

    def execute_plan(self, plan: BDIPlan) -> bool:
        """Execute a plan using VAL and update state."""
        pddl_actions = bdi_to_pddl_actions(plan, domain=self.domain)
        executor = PlanExecutor(
            domain_file=self.domain_file,
            problem_file=self.inst_file,
        )

        # If we have previously executed actions, prepend them
        total_actions = self.executed_actions + pddl_actions
        result = executor.execute(total_actions)

        if result.success:
            self.final_success = True
            return True

        # Update failure state for next replan
        self.executed_actions = result.executed_actions
        self.failed_action = result.failed_action
        self.failure_reasons = result.failure_reason or []
        return False

def run_batch_replanning(
    domain: str,
    max_instances: Optional[int] = None,
    output_dir: str = "runs/batch_replanning",
    max_rounds: int = 3,
    model: str = "qwen3.5-plus",
    dry_run: bool = False,
):
    """Main evaluation loop using batch API."""
    os.makedirs(output_dir, exist_ok=True)
    start_time = time.time()

    # 1. Load instances
    base_path = str(Path(__file__).parents[1] / "workspaces" / "planbench_data" / "plan-bench")
    all_inst_files = find_all_instances(base_path, domain=domain)
    if max_instances:
        all_inst_files = all_inst_files[:max_instances]

    instances: List[InstanceData] = []
    for f in all_inst_files:
        try:
            instances.append(InstanceData(f, domain))
        except Exception as e:
            logger.warning(f"Skipping {f}: {e}")

    logger.info(f"Loaded {len(instances)} instances for domain={domain}")

    engine = BatchEngine(model=model)

    # ============================================================== #
    # ROUND 0: Initial plan generation (batch)
    # ============================================================== #
    logger.info("=" * 60)
    logger.info("ROUND 0: Initial Plan Generation (Batch)")
    logger.info("=" * 60)

    batch_requests = []
    for inst in instances:
        messages = build_initial_plan_messages(inst.beliefs, inst.desire)
        batch_requests.append((inst.custom_id, messages))

    if dry_run:
        logger.info(f"[DRY RUN] Would submit {len(batch_requests)} requests")
        return

    batch_id = engine.submit(batch_requests, description=f"Initial {domain}")
    logger.info(f"Batch submitted: {batch_id}. Waiting for results...")
    raw_results = engine.wait_and_download(batch_id)
    logger.info(f"Batch complete. Got {len(raw_results)} results.")

    # Parse and execute
    pending_instances: List[InstanceData] = []
    for inst in instances:
        text = raw_results.get(inst.custom_id, "")
        if not text:
            inst.error = "No response from batch"
            continue

        plan = parse_plan_from_text(text)
        if not plan or len(plan.nodes) == 0:
            inst.error = "Failed to parse initial plan"
            pending_instances.append(inst)
            continue

        inst.plan = plan
        success = inst.execute_plan(plan)
        inst.initial_success = success

        if success:
            logger.info(f"  {inst.inst_name}: ✅ Initial plan succeeded")
        else:
            logger.info(
                f"  {inst.inst_name}: ❌ Failed at '{inst.failed_action}'"
            )
            pending_instances.append(inst)

    init_success = sum(1 for i in instances if i.initial_success)
    logger.info(
        f"Round 0 done: {init_success}/{len(instances)} succeeded, "
        f"{len(pending_instances)} need replanning"
    )

    # ============================================================== #
    # ROUNDS 1-N: Replanning (batch per round)
    # ============================================================== #
    for round_num in range(1, max_rounds + 1):
        if not pending_instances:
            logger.info("All instances succeeded! No more replanning needed.")
            break

        logger.info("=" * 60)
        logger.info(
            f"ROUND {round_num}: Replanning {len(pending_instances)} failures"
        )
        logger.info("=" * 60)

        # Build replanning requests
        replan_requests = []
        for inst in pending_instances:
            if inst.failed_action is None:
                # Parse failure; try initial plan again with different prompt
                messages = build_initial_plan_messages(inst.beliefs, inst.desire)
            else:
                messages = build_replan_messages(
                    beliefs=inst.beliefs,
                    desire=inst.desire,
                    executed_actions=inst.executed_actions,
                    failed_action=inst.failed_action,
                    failure_reasons=inst.failure_reasons,
                )
            replan_id = f"{inst.custom_id}_r{round_num}"
            replan_requests.append((replan_id, messages))

        batch_id = engine.submit(
            replan_requests,
            description=f"Replan R{round_num} {domain}",
        )
        logger.info(f"Replan batch submitted: {batch_id}. Waiting...")
        raw_results = engine.wait_and_download(batch_id)
        logger.info(f"Replan batch complete. Got {len(raw_results)} results.")

        # Parse and verify
        still_pending = []
        for inst in pending_instances:
            replan_id = f"{inst.custom_id}_r{round_num}"
            text = raw_results.get(replan_id, "")
            if not text:
                inst.error = f"No response in round {round_num}"
                still_pending.append(inst)
                continue

            recovery_plan = parse_plan_from_text(text)
            if not recovery_plan or len(recovery_plan.nodes) == 0:
                inst.error = f"Failed to parse recovery plan R{round_num}"
                still_pending.append(inst)
                continue

            inst.replanning_rounds = round_num
            success = inst.execute_plan(recovery_plan)

            if success:
                logger.info(f"  {inst.inst_name}: ✅ Repaired in round {round_num}")
            else:
                logger.info(
                    f"  {inst.inst_name}: ❌ Still failing at '{inst.failed_action}'"
                )
                still_pending.append(inst)

        repaired_this_round = len(pending_instances) - len(still_pending)
        logger.info(
            f"Round {round_num} done: repaired {repaired_this_round}, "
            f"{len(still_pending)} still pending"
        )
        pending_instances = still_pending

    # ============================================================== #
    # Results Summary
    # ============================================================== #
    total = len(instances)
    init_ok = sum(1 for i in instances if i.initial_success)
    final_ok = sum(1 for i in instances if i.final_success)
    repaired = final_ok - init_ok
    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print("RESULTS: Batch Dynamic Replanning")
    print("=" * 60)
    print(f"Domain:                {domain}")
    print(f"Total Instances:       {total}")
    print(f"Initial Accuracy:      {init_ok}/{total} ({init_ok/total:.1%})")
    print(f"Final Accuracy:        {final_ok}/{total} ({final_ok/total:.1%})")
    print(f"Replanning Lift:       +{repaired} instances")
    if (total - init_ok) > 0:
        repair_rate = repaired / (total - init_ok)
        print(f"Repair Rate:           {repair_rate:.1%}")
    print(f"Total Time:            {elapsed:.1f}s")
    print(f"Cost:                  ~50% of real-time API")

    # Save detailed results
    result_data = {
        "domain": domain,
        "model": model,
        "total_instances": total,
        "initial_success": init_ok,
        "final_success": final_ok,
        "repaired": repaired,
        "elapsed_seconds": round(elapsed, 1),
        "instances": [],
    }
    for inst in instances:
        result_data["instances"].append({
            "name": inst.inst_name,
            "file": inst.inst_file,
            "initial_success": inst.initial_success,
            "final_success": inst.final_success,
            "replanning_rounds": inst.replanning_rounds,
            "error": inst.error,
        })

    out_file = (
        f"{output_dir}/batch_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(out_file, "w") as f:
        json.dump(result_data, f, indent=2, default=str)
    print(f"Saved to: {out_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch Dynamic Replanning Evaluation")
    parser.add_argument(
        "--domain",
        type=str,
        required=True,
        choices=["blocksworld", "logistics", "depots"],
    )
    parser.add_argument("--max_instances", type=int, default=None)
    parser.add_argument("--max_rounds", type=int, default=3)
    parser.add_argument(
        "--model", type=str, default="qwen3.5-plus",
        help="Model name (must be in DashScope batch supported list)"
    )
    parser.add_argument("--output_dir", type=str, default="runs/batch_replanning")
    parser.add_argument(
        "--dry_run", action="store_true",
        help="Only parse instances and show what would be submitted"
    )
    args = parser.parse_args()

    run_batch_replanning(
        domain=args.domain,
        max_instances=args.max_instances,
        output_dir=args.output_dir,
        max_rounds=args.max_rounds,
        model=args.model,
        dry_run=args.dry_run,
    )
