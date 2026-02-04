#!/usr/bin/env python3
"""
PlanBench Full Benchmark Evaluation
====================================

Tests BDI-LLM on all PlanBench instances (4,430 PDDL problems)

Usage:
    # Test all instances in blocksworld
    python run_planbench_full.py --domain blocksworld --max_instances 100

    # Test all domains
    python run_planbench_full.py --all_domains --max_instances 50

    # Resume from checkpoint
    python run_planbench_full.py --domain blocksworld --resume results/checkpoint.json

Author: BDI-LLM Research
Date: 2026-02-03
"""

import sys
import os
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple
from datetime import datetime
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))

from src.bdi_llm.planner import BDIPlanner
from src.bdi_llm.schemas import BDIPlan
from src.bdi_llm.verifier import PlanVerifier
import networkx as nx


# ============================================================================
# PDDL PARSING
# ============================================================================

def parse_pddl_problem(pddl_file: str) -> dict:
    """Parse PDDL problem file"""
    with open(pddl_file, 'r') as f:
        content = f.read()

    # Extract problem name
    problem_match = re.search(r'\(define\s+\(problem\s+(.*?)\)', content)
    problem_name = problem_match.group(1) if problem_match else "unknown"

    # Extract objects
    objects_match = re.search(r':objects\s+(.*?)\)', content)
    objects = objects_match.group(1).split() if objects_match else []

    # Extract init state
    init_match = re.search(r':init\s+(.*?)\(:goal', content, re.DOTALL)
    if init_match:
        init_text = init_match.group(1)
        init_predicates = re.findall(r'\((.*?)\)', init_text)
    else:
        init_predicates = []

    # Extract goal
    goal_match = re.search(r':goal\s+\(and(.*?)\)\)', content, re.DOTALL)
    if goal_match:
        goal_text = goal_match.group(1)
        goal_predicates = re.findall(r'\((.*?)\)', goal_text)
    else:
        goal_predicates = []

    # Phase 1: Extract init_state for physics validation
    init_state = {
        'on_table': [],
        'on': [],
        'clear': [],
        'holding': None
    }

    for pred in init_predicates:
        parts = pred.split()
        if not parts:
            continue

        pred_name = parts[0]

        if pred_name == 'ontable' and len(parts) >= 2:
            init_state['on_table'].append(parts[1])
        elif pred_name == 'clear' and len(parts) >= 2:
            init_state['clear'].append(parts[1])
        elif pred_name == 'on' and len(parts) >= 3:
            init_state['on'].append((parts[1], parts[2]))
        elif pred_name == 'holding' and len(parts) >= 2:
            init_state['holding'] = parts[1]
        elif pred_name == 'handempty':
            init_state['holding'] = None

    return {
        'problem_name': problem_name,
        'objects': objects,
        'init': init_predicates,
        'goal': goal_predicates,
        'init_state': init_state  # NEW: For physics validation
    }


def pddl_to_natural_language(pddl_data: dict, domain: str = "blocksworld") -> Tuple[str, str]:
    """Convert PDDL to natural language (domain-specific)"""

    if domain == "blocksworld":
        return pddl_to_nl_blocksworld(pddl_data)
    elif domain == "logistics":
        return pddl_to_nl_logistics(pddl_data)
    elif domain == "depots":
        return pddl_to_nl_depots(pddl_data)
    else:
        # Generic fallback
        return pddl_to_nl_generic(pddl_data)


def pddl_to_nl_blocksworld(pddl_data: dict) -> Tuple[str, str]:
    """Blocksworld-specific conversion"""
    objects = pddl_data['objects']
    init = pddl_data['init']
    goal = pddl_data['goal']

    # Build beliefs
    beliefs_parts = []
    beliefs_parts.append(f"Blocksworld domain with {len(objects)} blocks: {', '.join(objects)}")

    # Parse init state
    on_table = []
    clear_blocks = []
    stacks = {}  # block -> block it's on

    for pred in init:
        parts = pred.split()
        if parts[0] == 'ontable':
            on_table.append(parts[1])
        elif parts[0] == 'clear':
            clear_blocks.append(parts[1])
        elif parts[0] == 'on' and len(parts) >= 3:
            stacks[parts[1]] = parts[2]

    beliefs_parts.append(f"Current state: All blocks on table: {', '.join(on_table)}")
    beliefs_parts.append("Your hand is empty")
    beliefs_parts.append("CRITICAL CONSTRAINTS:")
    beliefs_parts.append("- You can only pick up ONE block at a time")
    beliefs_parts.append("- You can only pick up a block if it has nothing on top (is 'clear')")
    beliefs_parts.append("- Available actions: pick-up, put-down, stack, unstack")

    beliefs = " ".join(beliefs_parts)

    # Build goal
    goal_stacks = []
    for pred in goal:
        parts = pred.split()
        if parts[0] == 'on' and len(parts) >= 3:
            goal_stacks.append(f"{parts[1]} on {parts[2]}")

    desire = f"Build tower: {' AND '.join(goal_stacks)}. Work step-by-step, one block at a time."

    return beliefs, desire


def pddl_to_nl_generic(pddl_data: dict) -> Tuple[str, str]:
    """Generic PDDL to NL conversion"""
    objects = pddl_data['objects']
    init = pddl_data['init']
    goal = pddl_data['goal']

    beliefs = f"Domain objects: {', '.join(objects)}. Initial state: {'; '.join(init[:10])}..."
    desire = f"Achieve goal: {'; '.join(goal[:5])}..."

    return beliefs, desire


def pddl_to_nl_logistics(pddl_data: dict) -> Tuple[str, str]:
    """Logistics domain conversion"""
    # TODO: Implement logistics-specific conversion
    return pddl_to_nl_generic(pddl_data)


def pddl_to_nl_depots(pddl_data: dict) -> Tuple[str, str]:
    """Depots domain conversion"""
    # TODO: Implement depots-specific conversion
    return pddl_to_nl_generic(pddl_data)


# ============================================================================
# BDI PLANNING
# ============================================================================

def bdi_to_pddl_actions(plan: BDIPlan, domain: str = "blocksworld") -> List[str]:
    """
    Convert BDI action nodes to PDDL action strings

    Args:
        plan: BDIPlan with action nodes
        domain: PDDL domain (default: blocksworld)

    Returns:
        List of PDDL action strings, e.g., ["(pick-up a)", "(stack a b)"]
    """
    pddl_actions = []

    # Get topological order of actions
    G = plan.to_networkx()
    try:
        import networkx as nx
        ordered_nodes = list(nx.topological_sort(G))
    except:
        # If cycles, use node order as-is
        ordered_nodes = [node.id for node in plan.nodes]

    # Convert each action to PDDL format
    for node_id in ordered_nodes:
        # Find the action node
        action_node = next((n for n in plan.nodes if n.id == node_id), None)
        if not action_node:
            continue

        action_type = action_node.action_type.lower()
        params = action_node.params

        if domain == "blocksworld":
            # Map BDI action types to PDDL actions
            if "pick" in action_type and "up" in action_type:
                block = params.get('block', params.get('object', ''))
                if block:
                    pddl_actions.append(f"(pick-up {block})")
            elif "put" in action_type and "down" in action_type:
                block = params.get('block', params.get('object', ''))
                if block:
                    pddl_actions.append(f"(put-down {block})")
            elif "stack" in action_type:
                block = params.get('block', params.get('from', ''))
                target = params.get('target', params.get('to', ''))
                if block and target:
                    pddl_actions.append(f"(stack {block} {target})")
            elif "unstack" in action_type:
                block = params.get('block', params.get('from', ''))
                target = params.get('target', params.get('to', ''))
                if block and target:
                    pddl_actions.append(f"(unstack {block} {target})")

    return pddl_actions


def generate_bdi_plan(beliefs: str, desire: str, init_state: Dict = None, timeout: int = 60) -> Tuple[BDIPlan, bool, dict]:
    """
    Generate plan with BDI-LLM and multi-layer verification

    Args:
        beliefs: Natural language beliefs
        desire: Natural language goal
        init_state: Initial state for physics validation (optional)
        timeout: Planning timeout

    Returns:
        (plan, is_valid, metrics)
    """
    from src.bdi_llm.symbolic_verifier import BlocksworldPhysicsValidator

    planner = BDIPlanner()

    start_time = time.time()
    metrics = {
        'generation_time': 0,
        'verification_layers': {
            'structural': {'valid': False, 'errors': []},
            'physics': {'valid': False, 'errors': []}
        },
        'overall_valid': False,
        'num_nodes': 0,
        'num_edges': 0
    }

    try:
        result = planner.generate_plan(beliefs=beliefs, desire=desire)
        plan = result.plan

        metrics['generation_time'] = time.time() - start_time

        # Layer 1: Structural verification
        G = plan.to_networkx()
        struct_valid, struct_errors = PlanVerifier.verify(G)

        metrics['verification_layers']['structural']['valid'] = struct_valid
        metrics['verification_layers']['structural']['errors'] = struct_errors
        metrics['num_nodes'] = len(plan.nodes)
        metrics['num_edges'] = len(plan.edges)

        # Layer 2a: Physics validation (if init_state provided)
        physics_valid = True
        physics_errors = []

        if init_state is not None:
            # Convert BDI plan to PDDL actions
            pddl_actions = bdi_to_pddl_actions(plan, domain="blocksworld")

            # Validate physics
            physics_validator = BlocksworldPhysicsValidator()
            physics_valid, physics_errors = physics_validator.validate_plan(
                pddl_actions, init_state
            )

        metrics['verification_layers']['physics']['valid'] = physics_valid
        metrics['verification_layers']['physics']['errors'] = physics_errors

        # Overall validation: must pass ALL layers
        overall_valid = struct_valid and physics_valid
        metrics['overall_valid'] = overall_valid

        return plan, overall_valid, metrics

    except Exception as e:
        metrics['generation_time'] = time.time() - start_time
        metrics['verification_layers']['structural']['errors'] = [str(e)]

        # Return empty plan
        plan = BDIPlan(goal_description=desire, nodes=[], edges=[])
        return plan, False, metrics


# ============================================================================
# BATCH EVALUATION
# ============================================================================

def find_all_instances(base_path: str, domain: str) -> List[str]:
    """Find all PDDL instance files for a domain"""
    domain_path = Path(base_path) / "instances" / domain

    instance_files = []
    for pattern in ["generated/instance-*.pddl", "generated_basic/instance-*.pddl"]:
        instance_files.extend(domain_path.glob(pattern))

    return sorted([str(f) for f in instance_files])


def run_batch_evaluation(
    domain: str,
    max_instances: int = None,
    resume_from: str = None,
    output_dir: str = "planbench_results"
) -> dict:
    """Run evaluation on all instances in a domain"""

    print(f"\n{'='*80}")
    print(f"  PLANBENCH FULL EVALUATION: {domain}")
    print(f"{'='*80}\n")

    # Setup
    base_path = "planbench_data/plan-bench"
    os.makedirs(output_dir, exist_ok=True)

    # Find instances
    instances = find_all_instances(base_path, domain)
    if max_instances:
        instances = instances[:max_instances]

    print(f"Found {len(instances)} instances")

    # Load checkpoint if resuming
    completed = set()
    results = {
        'domain': domain,
        'timestamp': datetime.now().isoformat(),
        'total_instances': len(instances),
        'results': []
    }

    if resume_from and os.path.exists(resume_from):
        print(f"Resuming from checkpoint: {resume_from}")
        with open(resume_from, 'r') as f:
            checkpoint = json.load(f)
            results['results'] = checkpoint.get('results', [])
            completed = set(r['instance_file'] for r in results['results'])
        print(f"Skipping {len(completed)} completed instances")

    # Evaluate each instance
    success_count = 0
    failed_count = 0

    for instance_file in tqdm(instances, desc=f"Evaluating {domain}"):
        # Skip if already completed
        if instance_file in completed:
            continue

        instance_result = {
            'instance_file': instance_file,
            'instance_name': Path(instance_file).stem,
            'timestamp': datetime.now().isoformat()
        }

        try:
            # Parse PDDL
            pddl_data = parse_pddl_problem(instance_file)
            instance_result['pddl_data'] = {
                'problem_name': pddl_data['problem_name'],
                'num_objects': len(pddl_data['objects']),
                'num_init': len(pddl_data['init']),
                'num_goals': len(pddl_data['goal'])
            }

            # Convert to NL
            beliefs, desire = pddl_to_natural_language(pddl_data, domain)
            instance_result['beliefs'] = beliefs[:200] + "..."  # Truncate for storage
            instance_result['desire'] = desire[:200] + "..."

            # Generate plan with init_state for physics validation
            init_state = pddl_data.get('init_state', None)
            plan, is_valid, metrics = generate_bdi_plan(beliefs, desire, init_state)

            instance_result['bdi_metrics'] = metrics
            instance_result['success'] = is_valid

            if is_valid:
                success_count += 1
            else:
                failed_count += 1

        except Exception as e:
            instance_result['success'] = False
            instance_result['error'] = str(e)
            failed_count += 1

        results['results'].append(instance_result)

        # Save checkpoint every 10 instances
        if len(results['results']) % 10 == 0:
            checkpoint_file = f"{output_dir}/checkpoint_{domain}.json"
            with open(checkpoint_file, 'w') as f:
                json.dump(results, f, indent=2)

    # Final statistics with comparative analysis
    # Count structural-only vs multi-layer success
    structural_only_success = sum(
        1 for r in results['results']
        if r.get('bdi_metrics', {}).get('verification_layers', {}).get('structural', {}).get('valid', False)
    )
    overall_success = sum(
        1 for r in results['results']
        if r.get('bdi_metrics', {}).get('overall_valid', False)
    )
    physics_caught_errors = structural_only_success - overall_success

    results['summary'] = {
        'total_evaluated': len(results['results']),
        'success_count': success_count,
        'failed_count': failed_count,
        'success_rate': success_count / len(results['results']) if results['results'] else 0,
        'avg_generation_time': sum(
            r.get('bdi_metrics', {}).get('generation_time', 0)
            for r in results['results']
        ) / len(results['results']) if results['results'] else 0,
        'structural_only_success': structural_only_success,
        'physics_caught_errors': physics_caught_errors
    }

    # Save final results
    output_file = f"{output_dir}/results_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*80}")
    print(f"  EVALUATION COMPLETE")
    print(f"{'='*80}")
    print(f"\nDomain: {domain}")
    print(f"Total instances: {len(results['results'])}")
    print(f"\n--- Multi-Layer Verification Comparison ---")
    print(f"Structural-only success: {structural_only_success} ({structural_only_success/len(results['results'])*100:.1f}%)")
    print(f"Multi-layer success: {overall_success} ({overall_success/len(results['results'])*100:.1f}%)")
    print(f"Physics caught: {physics_caught_errors} additional errors")
    print(f"\nFinal success: {success_count} ({success_count/len(results['results'])*100:.1f}%)")
    print(f"Failed: {failed_count}")
    print(f"\nResults saved to: {output_file}")

    return results


# ============================================================================
# MAIN
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="PlanBench Full Benchmark Evaluation")
    parser.add_argument("--domain", type=str,
                       choices=["blocksworld", "logistics", "depots",
                               "obfuscated_deceptive_logistics", "obfuscated_randomized_logistics"],
                       help="Domain to evaluate")
    parser.add_argument("--all_domains", action="store_true",
                       help="Evaluate all domains")
    parser.add_argument("--max_instances", type=int, default=None,
                       help="Maximum number of instances per domain (default: all)")
    parser.add_argument("--resume", type=str, default=None,
                       help="Resume from checkpoint file")
    parser.add_argument("--output_dir", type=str, default="planbench_results",
                       help="Output directory for results")

    args = parser.parse_args()

    # Check API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("❌ ERROR: OPENAI_API_KEY not set")
        print("   export OPENAI_API_KEY=your-key")
        sys.exit(1)

    # Determine domains to evaluate
    if args.all_domains:
        domains = ["blocksworld", "logistics", "depots"]
    elif args.domain:
        domains = [args.domain]
    else:
        print("❌ ERROR: Must specify --domain or --all_domains")
        sys.exit(1)

    # Run evaluation
    all_results = {}
    for domain in domains:
        results = run_batch_evaluation(
            domain=domain,
            max_instances=args.max_instances,
            resume_from=args.resume,
            output_dir=args.output_dir
        )
        all_results[domain] = results

    # Print overall summary
    if len(domains) > 1:
        print(f"\n{'='*80}")
        print(f"  OVERALL SUMMARY")
        print(f"{'='*80}\n")

        for domain, results in all_results.items():
            summary = results['summary']
            print(f"{domain}:")
            print(f"  Success: {summary['success_count']}/{summary['total_evaluated']} "
                  f"({summary['success_rate']*100:.1f}%)")
            print(f"  Avg time: {summary['avg_generation_time']:.2f}s\n")


if __name__ == "__main__":
    main()
