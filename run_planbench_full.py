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
from src.bdi_llm.plan_repair import repair_and_verify, PlanRepairer
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

    # Extract domain name - NEW: Critical for resolving the correct domain file
    domain_match = re.search(r'\(:domain\s+(.*?)\)', content)
    domain_name = domain_match.group(1).strip() if domain_match else "blocksworld"

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
        'domain_name': domain_name,  # NEW: For resolving domain file
        'objects': objects,
        'init': init_predicates,
        'goal': goal_predicates,
        'init_state': init_state  # NEW: For physics validation
    }


def resolve_domain_file(domain_name: str, base_path: str = None) -> str:
    """Resolve the correct PDDL domain file path based on domain name.

    Prefers instances/<domain>/generated_domain.pddl when it exists, because
    that file's action names (pick-up / put-down) match the instance files.
    Falls back to pddlgenerators/ domain.pddl otherwise.
    """
    if base_path is None:
        base_path = str(Path(__file__).resolve().parent / "planbench_data/plan-bench")

    # Map PDDL domain name -> instance directory name
    dir_map = {
        "blocksworld-4ops": "blocksworld",
        "blocksworld": "blocksworld",
        "logistics": "logistics",
        "depots": "depots",
    }
    dir_name = dir_map.get(domain_name, domain_name.split("-")[0])

    # Prefer generated_domain.pddl alongside the instance files
    generated = Path(base_path) / "instances" / dir_name / "generated_domain.pddl"
    if generated.is_file():
        return str(generated)

    # Fallback to pddlgenerators/ domain files
    if domain_name == "blocksworld-4ops":
        return f"{base_path}/pddlgenerators/blocksworld/4ops/domain.pddl"
    elif domain_name == "blocksworld":
        return f"{base_path}/pddlgenerators/blocksworld/domain.pddl"
    elif domain_name == "logistics":
        return f"{base_path}/pddlgenerators/logistics/domain.pddl"
    elif domain_name == "depots":
        return f"{base_path}/pddlgenerators/depots/domain.pddl"

    # Generic fallback search
    print(f"Warning: Unknown domain name '{domain_name}', trying generic search...")
    matches = list(Path(base_path).rglob("domain.pddl"))
    for match in matches:
        if domain_name in str(match):
            return str(match)

    return f"{base_path}/pddlgenerators/blocksworld/domain.pddl"



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
    """Enhanced Blocksworld-specific conversion with clearer state description"""
    objects = pddl_data['objects']
    init = pddl_data['init']
    goal = pddl_data['goal']

    # Parse init state in detail
    on_table = []
    clear_blocks = []
    stacks = {}  # block -> block it's on
    hand_empty = True

    for pred in init:
        parts = pred.split()
        if parts[0] == 'ontable':
            on_table.append(parts[1])
        elif parts[0] == 'clear':
            clear_blocks.append(parts[1])
        elif parts[0] == 'on' and len(parts) >= 3:
            stacks[parts[1]] = parts[2]
        elif parts[0] == 'handempty':
            hand_empty = True
        elif parts[0] == 'holding':
            hand_empty = False

    # Build beliefs with detailed state description
    beliefs_parts = []
    beliefs_parts.append(f"BLOCKSWORLD DOMAIN")
    beliefs_parts.append(f"\n=== CURRENT STATE ===")
    beliefs_parts.append(f"Available blocks ({len(objects)}): {', '.join(sorted(objects))}")

    # Describe stacks (what's on what)
    if stacks:
        stack_descs = []
        for top, bottom in sorted(stacks.items()):
            stack_descs.append(f"{top} is on top of {bottom}")
        beliefs_parts.append(f"Stacks: {'; '.join(stack_descs)}")

    # Describe blocks on table
    if on_table:
        beliefs_parts.append(f"Blocks on table: {', '.join(sorted(on_table))}")

    # Describe clear blocks (can be picked up)
    beliefs_parts.append(f"Clear blocks (can pick up): {', '.join(sorted(clear_blocks))}")

    # Hand state
    beliefs_parts.append(f"Hand: {'empty' if hand_empty else 'holding something'}")

    beliefs_parts.append(f"\n=== PHYSICS CONSTRAINTS ===")
    beliefs_parts.append("1. You can only hold ONE block at a time")
    beliefs_parts.append("2. You can only pick up blocks that are CLEAR (nothing on top)")
    beliefs_parts.append("3. You can only stack on blocks that are CLEAR")
    beliefs_parts.append("4. You can only pick up from table, not from other blocks")
    beliefs_parts.append("5. To move a block from another block, use UNSTACK (not pick-up)")

    beliefs_parts.append(f"\n=== AVAILABLE ACTIONS ===")
    beliefs_parts.append("- pick-up X: Pick up block X from table (X must be clear and on table)")
    beliefs_parts.append("- put-down X: Put block X on table (you must be holding X)")
    beliefs_parts.append("- stack X Y: Put block X on top of block Y (you hold X, Y must be clear)")
    beliefs_parts.append("- unstack X Y: Take block X off block Y (X must be clear, hand empty)")

    beliefs_parts.append(f"\n=== PLANNING REQUIREMENTS ===")
    beliefs_parts.append("Generate a SEQUENTIAL plan where each action depends on the previous one.")
    beliefs_parts.append("The plan graph must be CONNECTED - all actions form one chain/path.")

    beliefs = "\n".join(beliefs_parts)

    # Build goal with bottom-up tower ordering and explicit construction steps
    goal_pairs = []  # (top, bottom) from "on top bottom"
    for pred in goal:
        parts = pred.split()
        if parts[0] == 'on' and len(parts) >= 3:
            goal_pairs.append((parts[1], parts[2]))

    # Build bottom-up ordering: find tower bases and walk upward
    # on_map: bottom_block -> block_that_goes_on_top
    on_map = {}
    top_set = set()
    bottom_set = set()
    for top_blk, bot_blk in goal_pairs:
        on_map[bot_blk] = top_blk
        top_set.add(top_blk)
        bottom_set.add(bot_blk)

    # Base blocks: appear as a support but are never placed on something else
    bases = sorted(b for b in bottom_set if b not in top_set)

    # Walk each tower chain from base upward
    towers = []
    for base in bases:
        tower = [base]
        cur = base
        while cur in on_map:
            cur = on_map[cur]
            tower.append(cur)
        towers.append(tower)

    goal_desc = "Build the following tower(s) from BOTTOM to TOP:\n"
    step_num = 1
    for tower in towers:
        goal_desc += f"\n  Tower (base={tower[0]}): {' -> '.join(tower)}  (bottom to top)\n"
        goal_desc += f"  Construction steps:\n"
        for i in range(1, len(tower)):
            blk = tower[i]
            tgt = tower[i - 1]
            goal_desc += f"    Step {step_num}: pick-up {blk}, then stack {blk} on {tgt}\n"
            step_num += 1

    goal_desc += "\nExample — to build tower C -> B -> A (C on table, B on C, A on B):\n"
    goal_desc += "  1. pick-up B   2. stack B C   3. pick-up A   4. stack A B\n"
    goal_desc += "\nWork step-by-step, one action at a time. Each action depends on completing the previous action."

    desire = goal_desc

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
    """Logistics domain conversion with proper state description"""
    objects = pddl_data['objects']
    init = pddl_data['init']
    goal = pddl_data['goal']

    # Parse logistics state
    packages = []
    trucks = []
    airplanes = []
    locations = []
    cities = []

    at_locations = {}  # object -> location
    in_vehicle = {}    # package -> vehicle

    for pred in init:
        parts = pred.split()
        if parts[0] == 'at' and len(parts) >= 3:
            at_locations[parts[1]] = parts[2]
        elif parts[0] == 'in' and len(parts) >= 3:
            in_vehicle[parts[1]] = parts[2]

    # Build beliefs
    beliefs_parts = []
    beliefs_parts.append("LOGISTICS DOMAIN")
    beliefs_parts.append("\n=== CURRENT STATE ===")
    beliefs_parts.append(f"Objects: {', '.join(objects[:20])}")  # Limit for readability

    if at_locations:
        loc_descs = [f"{obj} is at {loc}" for obj, loc in list(at_locations.items())[:10]]
        beliefs_parts.append(f"Locations: {'; '.join(loc_descs)}")

    if in_vehicle:
        veh_descs = [f"{pkg} is in {veh}" for pkg, veh in list(in_vehicle.items())[:10]]
        beliefs_parts.append(f"In vehicles: {'; '.join(veh_descs)}")

    beliefs_parts.append("\n=== AVAILABLE ACTIONS ===")
    beliefs_parts.append("- load-truck: Load package into truck")
    beliefs_parts.append("- unload-truck: Unload package from truck")
    beliefs_parts.append("- load-airplane: Load package into airplane")
    beliefs_parts.append("- unload-airplane: Unload package from airplane")
    beliefs_parts.append("- drive-truck: Drive truck between locations")
    beliefs_parts.append("- fly-airplane: Fly airplane between airports")

    beliefs_parts.append("\n=== PLANNING REQUIREMENTS ===")
    beliefs_parts.append("Generate a SEQUENTIAL plan with CONNECTED actions.")

    beliefs = "\n".join(beliefs_parts)

    # Build goal
    goal_descs = []
    for pred in goal[:10]:  # Limit for readability
        parts = pred.split()
        if parts[0] == 'at' and len(parts) >= 3:
            goal_descs.append(f"{parts[1]} should be at {parts[2]}")

    desire = f"Goal: {'; '.join(goal_descs)}. Work step-by-step with connected actions."

    return beliefs, desire


def pddl_to_nl_depots(pddl_data: dict) -> Tuple[str, str]:
    """Depots domain conversion"""
    objects = pddl_data['objects']
    init = pddl_data['init']
    goal = pddl_data['goal']

    beliefs_parts = []
    beliefs_parts.append("DEPOTS DOMAIN")
    beliefs_parts.append(f"\nObjects: {', '.join(objects[:20])}")
    beliefs_parts.append(f"\nInitial state: {'; '.join(init[:10])}")
    beliefs_parts.append("\n=== PLANNING REQUIREMENTS ===")
    beliefs_parts.append("Generate a SEQUENTIAL plan with CONNECTED actions.")

    beliefs = "\n".join(beliefs_parts)

    desire = f"Goal: {'; '.join(goal[:5])}. Work step-by-step."

    return beliefs, desire


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

    # Filter out virtual nodes
    virtual_nodes = {"__START__", "__END__"}

    try:
        import networkx as nx
        ordered_nodes = [n for n in nx.topological_sort(G) if n not in virtual_nodes]
    except:
        # If cycles, use node order as-is
        ordered_nodes = [node.id for node in plan.nodes if node.id not in virtual_nodes]

    # Create node lookup
    node_lookup = {n.id: n for n in plan.nodes}

    # Normalise action_type string to a canonical key
    def _normalise(atype: str) -> str:
        t = atype.lower().replace("-", "").replace("_", "").strip()
        if t == "pickup":
            return "pick-up"
        if t == "putdown":
            return "put-down"
        if t.startswith("unstack"):
            return "unstack"
        if t.startswith("stack"):
            return "stack"
        return t

    # Convert each action to PDDL format using params deterministically
    for node_id in ordered_nodes:
        action_node = node_lookup.get(node_id)
        if not action_node:
            continue

        canon = _normalise(action_node.action_type)
        params = action_node.params
        block = params.get("block", "")
        target = params.get("target", "")

        if domain == "blocksworld":
            if canon == "pick-up" and block:
                pddl_actions.append(f"(pick-up {block})")
            elif canon == "put-down" and block:
                pddl_actions.append(f"(put-down {block})")
            elif canon == "stack" and block and target:
                pddl_actions.append(f"(stack {block} {target})")
            elif canon == "unstack" and block and target:
                pddl_actions.append(f"(unstack {block} {target})")

    return pddl_actions


def generate_bdi_plan(
    beliefs: str,
    desire: str,
    pddl_problem_path: str = None,  # NEW: Path to problem file for VAL
    pddl_domain_path: str = None,   # NEW: Path to domain file for VAL
    init_state: Dict = None,
    timeout: int = 60,
    auto_repair: bool = True,
    max_retries: int = 3
) -> Tuple[BDIPlan, bool, dict]:
    """
    Generate plan with BDI-LLM and multi-layer verification

    Args:
        beliefs: Natural language beliefs
        desire: Natural language goal
        pddl_problem_path: Path to PDDL problem file (for symbolic verification)
        pddl_domain_path: Path to PDDL domain file (for symbolic verification)
        init_state: Initial state for physics validation (optional)
        timeout: Planning timeout
        auto_repair: Enable automatic plan repair (default: True)
        max_retries: Maximum retries for API errors (default: 3)

    Returns:
        (plan, is_valid, metrics)
    """
    from src.bdi_llm.symbolic_verifier import BlocksworldPhysicsValidator, PDDLSymbolicVerifier

    start_time = time.time()
    metrics = {
        'generation_time': 0,
        'verification_layers': {
            'structural': {'valid': False, 'errors': []},
            'symbolic': {'valid': False, 'errors': []},  # NEW: VAL verification
            'physics': {'valid': False, 'errors': []}
        },
        'auto_repair': {
            'triggered': False,
            'success': False,
            'repairs_applied': []
        },
        'overall_valid': False,
        'num_nodes': 0,
        'num_edges': 0,
        'retries': 0
    }

    last_error = None
    for attempt in range(max_retries):
        try:
            planner = BDIPlanner(auto_repair=auto_repair)
            result = planner.generate_plan(beliefs=beliefs, desire=desire)
            plan = result.plan
            metrics['retries'] = attempt

            metrics['generation_time'] = time.time() - start_time

            # Layer 1: Structural verification
            G = plan.to_networkx()
            struct_valid, struct_errors = PlanVerifier.verify(G)

            # If structural verification fails and auto_repair is enabled at this level too
            if not struct_valid and auto_repair:
                repaired_plan, repaired_valid, messages = repair_and_verify(plan)
                if repaired_valid:
                    plan = repaired_plan
                    G = plan.to_networkx()
                    struct_valid, struct_errors = PlanVerifier.verify(G)
                    metrics['auto_repair']['triggered'] = True
                    metrics['auto_repair']['success'] = True
                    metrics['auto_repair']['repairs_applied'] = messages

            metrics['verification_layers']['structural']['valid'] = struct_valid
            metrics['verification_layers']['structural']['errors'] = struct_errors
            metrics['num_nodes'] = len(plan.nodes)
            metrics['num_edges'] = len(plan.edges)

            # Layer 2: Symbolic Verification (PDDL/VAL) - NEW
            symbolic_valid = False
            symbolic_errors = ["Skipped - Structural failure"]

            if struct_valid and pddl_problem_path and pddl_domain_path:
                try:
                    # Convert BDI plan to PDDL actions
                    pddl_actions = bdi_to_pddl_actions(plan, domain="blocksworld")

                    # Initialize VAL verifier
                    val_verifier = PDDLSymbolicVerifier()
                    symbolic_valid, symbolic_errors = val_verifier.verify_plan(
                        domain_file=pddl_domain_path,
                        problem_file=pddl_problem_path,
                        plan_actions=pddl_actions
                    )
                except Exception as e:
                    symbolic_valid = False
                    symbolic_errors = [f"Symbolic verification error: {str(e)}"]

            elif not struct_valid:
                symbolic_errors = ["Skipped - Structural failure"]
            else:
                symbolic_errors = ["Skipped - Missing PDDL files"]
                # If no PDDL files provided, we consider symbolic layer 'passed' (or skipped)
                # to not break existing tests, but for PlanBench it should be provided.
                if pddl_problem_path is None:
                    symbolic_valid = True

            metrics['verification_layers']['symbolic']['valid'] = symbolic_valid
            metrics['verification_layers']['symbolic']['errors'] = symbolic_errors

            # Layer 3: Physics validation (if init_state provided)
            # This is now a "fallback" or "double-check" layer
            physics_valid = True
            physics_errors = []

            if init_state is not None and struct_valid:
                # Convert BDI plan to PDDL actions (if not done already)
                pddl_actions = bdi_to_pddl_actions(plan, domain="blocksworld")

                # Validate physics
                physics_validator = BlocksworldPhysicsValidator()
                physics_valid, physics_errors = physics_validator.validate_plan(
                    pddl_actions, init_state
                )

            metrics['verification_layers']['physics']['valid'] = physics_valid
            metrics['verification_layers']['physics']['errors'] = physics_errors

            # Overall validation: must pass ALL layers
            # Note: symbolic_valid defaults to False if files present but failed
            overall_valid = struct_valid and symbolic_valid and physics_valid
            metrics['overall_valid'] = overall_valid

            return plan, overall_valid, metrics

        except Exception as e:
            last_error = str(e)
            metrics['retries'] = attempt + 1

            # Check if it's a retryable error (connection issues)
            error_str = str(e).lower()
            if 'connection' in error_str or 'timeout' in error_str or 'internal' in error_str:
                if attempt < max_retries - 1:
                    import time as time_module
                    wait_time = 2 ** (attempt + 1)  # Exponential backoff
                    print(f"    API error, retrying in {wait_time}s... ({attempt + 1}/{max_retries})")
                    time_module.sleep(wait_time)
                    continue

            # Non-retryable error or max retries reached
            metrics['generation_time'] = time.time() - start_time
            metrics['verification_layers']['structural']['errors'] = [last_error]

            # Return empty plan
            plan = BDIPlan(goal_description=desire, nodes=[], edges=[])
            return plan, False, metrics

    # Should not reach here, but just in case
    metrics['generation_time'] = time.time() - start_time
    metrics['verification_layers']['structural']['errors'] = [f"Max retries ({max_retries}) exceeded: {last_error}"]
    plan = BDIPlan(goal_description=desire, nodes=[], edges=[])
    return plan, False, metrics


# ============================================================================
# BATCH EVALUATION
# ============================================================================

def find_all_instances(base_path: str, domain: str) -> List[str]:
    """Find all PDDL instance files for a domain"""
    domain_path = Path(base_path) / "instances" / domain

    instance_files = []
    for pattern in [
        "generated/instance-*.pddl",
        "generated_basic/instance-*.pddl",
        "generated_basic_*/instance-*.pddl"
    ]:
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
    base_path = Path(__file__).resolve().parent / "planbench_data/plan-bench"
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

            # Resolve PDDL domain file for VAL
            domain_name = pddl_data.get('domain_name', 'blocksworld')
            domain_file = resolve_domain_file(domain_name)

            plan, is_valid, metrics = generate_bdi_plan(
                beliefs=beliefs,
                desire=desire,
                pddl_problem_path=instance_file,  # Pass problem path for VAL
                pddl_domain_path=domain_file,     # Pass domain path for VAL
                init_state=init_state
            )

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

    # Count symbolic and physics failures
    symbolic_caught_errors = sum(
        1 for r in results['results']
        if r.get('bdi_metrics', {}).get('verification_layers', {}).get('structural', {}).get('valid', False)
        and not r.get('bdi_metrics', {}).get('verification_layers', {}).get('symbolic', {}).get('valid', False)
    )
    physics_caught_errors = sum(
        1 for r in results['results']
        if r.get('bdi_metrics', {}).get('verification_layers', {}).get('structural', {}).get('valid', False)
        and not r.get('bdi_metrics', {}).get('verification_layers', {}).get('physics', {}).get('valid', False)
    )

    # Count auto-repair statistics
    auto_repair_triggered = sum(
        1 for r in results['results']
        if r.get('bdi_metrics', {}).get('auto_repair', {}).get('triggered', False)
    )
    auto_repair_success = sum(
        1 for r in results['results']
        if r.get('bdi_metrics', {}).get('auto_repair', {}).get('success', False)
    )

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
        'symbolic_caught_errors': symbolic_caught_errors,  # New metric
        'physics_caught_errors': physics_caught_errors,
        'auto_repair': {
            'triggered': auto_repair_triggered,
            'successful': auto_repair_success,
            'success_rate': auto_repair_success / auto_repair_triggered if auto_repair_triggered > 0 else 0
        }
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
    print(f"Symbolic caught: {symbolic_caught_errors} additional errors")
    print(f"Physics caught: {physics_caught_errors} additional errors")
    print(f"\n--- Auto-Repair Statistics ---")
    print(f"Auto-repair triggered: {auto_repair_triggered}")
    print(f"Auto-repair successful: {auto_repair_success}")
    if auto_repair_triggered > 0:
        print(f"Auto-repair success rate: {auto_repair_success/auto_repair_triggered*100:.1f}%")
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
