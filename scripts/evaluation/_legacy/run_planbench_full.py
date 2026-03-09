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
    python run_planbench_full.py --domain blocksworld --resume runs/checkpoint.json

Author: BDI-LLM Research
Date: 2026-02-03
"""

import sys
import os
import json
import re
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

import dspy

from bdi_llm.planner import BDIPlanner, configure_dspy
from bdi_llm.planner.domain_spec import (
    DomainSpec,
    decode_planbench_literals,
    extract_actions_from_pddl,
    load_planbench_domain_intro,
    encode_planbench_symbol,
)
from bdi_llm.config import Config
from bdi_llm.schemas import BDIPlan
from bdi_llm.planning_task import PDDLPlanSerializer, PlanningTask
from bdi_llm.verifier import PlanVerifier
from bdi_llm.plan_repair import repair_and_verify, PlanRepairer
import networkx as nx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLANBENCH_ROOT = PROJECT_ROOT / "workspaces" / "planbench_data" / "plan-bench"
BUILTIN_PLAN_DOMAINS = {"blocksworld", "logistics", "depots"}
EXECUTION_STAGES = {"baseline", "bdi", "bdi-repair"}
STAGE_RESULT_KEYS = {
    "baseline": "baseline_result",
    "bdi": "bdi_initial_result",
    "bdi-repair": "bdi_repair_result",
}


class GenerateBaselineActionSequence(dspy.Signature):
    """Generate a direct grounded PDDL action sequence without BDI graph scaffolding.

    Output requirements:
    - Return ONLY grounded PDDL actions, one per line.
    - Each line must look like `(action-name arg1 arg2 ...)`.
    - No numbering, JSON, markdown fences, or explanations.
    - Use the available domain actions and object names from the provided task context.
    """

    beliefs: str = dspy.InputField(desc="Current state in natural language")
    desire: str = dspy.InputField(desc="Goal description in natural language")
    domain_context: str = dspy.InputField(
        desc="Optional action schema summary and domain predicates. Empty if unavailable.",
        default="",
    )
    allowed_actions: str = dspy.InputField(
        desc="Comma-separated grounded action names allowed in this domain.",
        default="",
    )
    allowed_objects: str = dspy.InputField(
        desc="Comma-separated object names allowed in this problem instance.",
        default="",
    )
    output_rules: str = dspy.InputField(
        desc="Hard output constraints. Follow literally.",
        default="",
    )
    plan_actions: str = dspy.OutputField(
        desc="A direct grounded PDDL action sequence, one action per line, no extra text"
    )


def resolve_execution_mode(execution_mode: str | None = None) -> str:
    """Resolve execution stage from explicit arg or environment."""
    mode = (execution_mode or os.environ.get("AGENT_EXECUTION_MODE") or "bdi-repair")
    mode = str(mode).strip().lower()
    if mode not in EXECUTION_STAGES:
        raise ValueError(f"Unsupported execution mode: {mode}")
    return mode


def execution_mode_flags(execution_mode: str) -> dict[str, bool]:
    """Return feature gates for one benchmark stage."""
    mode = resolve_execution_mode(execution_mode)
    return {
        "run_baseline": True,
        "run_bdi": mode in {"bdi", "bdi-repair"},
        "run_bdi_repair": mode == "bdi-repair",
        "structural_check": True,
        "structural_auto_repair": mode == "bdi-repair",
        "symbolic_check": True,
        "physics_check": False,
        "val_repair": mode == "bdi-repair",
    }


def checkpoint_path(output_dir: str, domain: str, execution_mode: str) -> str:
    """Build a per-domain pipeline checkpoint path."""
    return f"{output_dir}/checkpoint_{domain}_pipeline.json"


def stage_result_key(execution_mode: str) -> str:
    return STAGE_RESULT_KEYS[resolve_execution_mode(execution_mode)]

# MLflow integration for experiment tracking
try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    print("⚠️  MLflow not installed. Install with: pip install mlflow")
    print("   Experiment tracking will be disabled.")

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

    # Extract objects (supports typed PDDL format: "obj1 obj2 - Type")
    objects_match = re.search(r':objects\s+(.*?)\)', content, re.DOTALL)
    objects = []
    typed_objects = {}  # object_name -> type_name
    if objects_match:
        objects_text = objects_match.group(1)
        # Parse typed object declarations: "obj1 obj2 - Type"
        typed_pattern = re.findall(r'([\w\s]+?)\s*-\s*(\w+)', objects_text)
        if typed_pattern:
            for names_str, type_name in typed_pattern:
                for name in names_str.split():
                    name = name.strip()
                    if name:
                        objects.append(name)
                        typed_objects[name] = type_name
        else:
            # Fallback: untyped objects (e.g., blocksworld)
            objects = objects_text.split()

    # Extract init state
    init_match = re.search(r':init\s+(.*?)\(:goal', content, re.DOTALL)
    if init_match:
        init_text = init_match.group(1)
        init_predicates = re.findall(r'\((.*?)\)', init_text)
    else:
        init_predicates = []

    # Extract goal
    goal_match = re.search(r':goal\s*\(and\s*((?:\([^)]+\)\s*)+)\)', content, re.DOTALL)
    if goal_match:
        goal_content = goal_match.group(1)
        goal_predicates = re.findall(r'\(([^)]+)\)', goal_content)
    else:
        single_goal_match = re.search(r':goal\s*(\([^)]+\))', content, re.DOTALL)
        if single_goal_match:
            goal_predicates = re.findall(r'\(([^)]+)\)', single_goal_match.group(1))
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
        'typed_objects': typed_objects,  # NEW: object_name -> type_name mapping
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
        base_path = str(PLANBENCH_ROOT)

    # Map PDDL domain name -> instance directory name
    dir_map = {
        "blocksworld-4ops": "blocksworld",
        "blocksworld": "blocksworld",
        "logistics": "logistics",
        "depots": "depots",
        "obfuscated_deceptive_logistics": "obfuscated_deceptive_logistics",
        "obfuscated_randomized_logistics": "obfuscated_randomized_logistics",
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

    domain_intro = load_planbench_domain_intro(domain)
    if domain.startswith("obfuscated_") and domain_intro:
        return pddl_to_nl_planbench_style(pddl_data, domain_intro)

    if domain == "blocksworld":
        return pddl_to_nl_blocksworld(pddl_data)
    elif domain == "logistics":
        return pddl_to_nl_logistics(pddl_data)
    elif domain == "depots":
        return pddl_to_nl_depots(pddl_data)
    else:
        # Generic fallback
        return pddl_to_nl_generic(pddl_data)


def _natural_predicate_list(predicates: List[str]) -> str:
    if not predicates:
        return "nothing"
    if len(predicates) == 1:
        return predicates[0]
    if len(predicates) == 2:
        return f"{predicates[0]} and {predicates[1]}"
    return ", ".join(predicates[:-1]) + f" and {predicates[-1]}"


def pddl_to_nl_planbench_style(pddl_data: dict, domain_intro: str) -> Tuple[str, str]:
    """Use the same domain-intro framing style as PlanBench prompt generation."""
    domain_name = str(pddl_data.get('domain_name', '')).strip()
    init_preds = decode_planbench_literals(domain_name, pddl_data.get('init', []))
    goal_preds = decode_planbench_literals(domain_name, pddl_data.get('goal', []))
    init_text = _natural_predicate_list(init_preds)
    goal_text = _natural_predicate_list(goal_preds)

    beliefs = (
        f"{domain_intro.strip()}\n\n"
        f"As initial conditions I have that, {init_text}."
    )
    desire = (
        f"My goal is to have that {goal_text}.\n\n"
        "Generate a sequential connected plan using only the available actions."
    )
    return beliefs, desire

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

    # Track goal pairs
    goal_pairs = set()
    for pred in goal:
        parts = pred.split()
        if parts[0] == 'on' and len(parts) >= 3:
            goal_pairs.add((parts[1], parts[2]))

    # Identify goal tops (any block that is a 'top' in a goal pair)
    # If a block is NOT in this set, it should be on the table in the goal state.
    goal_tops = {t for t, b in goal_pairs}

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

    # Describe stacks (what's on what) - ENHANCED
    if stacks:
        stack_descs = []
        for top, bottom in sorted(stacks.items()):
            stack_descs.append(f"{top} is on top of {bottom}")
        beliefs_parts.append(f"Current stacks: {'; '.join(stack_descs)}")
        beliefs_parts.append(f"⚠️  IMPORTANT: These blocks are STACKED. To move them, you MUST unstack first!")
    else:
        beliefs_parts.append(f"Current stacks: None (all blocks are on table)")

    # Describe blocks on table
    if on_table:
        beliefs_parts.append(f"Blocks on table: {', '.join(sorted(on_table))}")

    # Describe clear blocks (can be picked up)
    beliefs_parts.append(f"Clear blocks (nothing on top): {', '.join(sorted(clear_blocks))}")

    # Hand state
    beliefs_parts.append(f"Hand: {'empty' if hand_empty else 'holding something'}")

    beliefs_parts.append(f"\n=== CRITICAL RULES FOR INITIAL STACKS ===")
    beliefs_parts.append("⚠️  If a block is ON another block in the initial state:")
    beliefs_parts.append("   1. You CANNOT pick-up that block directly")
    beliefs_parts.append("   2. You MUST use 'unstack X Y' to remove X from Y first")
    beliefs_parts.append("   3. After unstacking, you are HOLDING the block")
    beliefs_parts.append("   4. Then you can put-down or stack it elsewhere")
    beliefs_parts.append("")
    beliefs_parts.append("Example: If initial state has '(on B A)' and you want to move B:")
    beliefs_parts.append("   ✓ Correct: unstack B A → put-down B (or stack B somewhere)")
    beliefs_parts.append("   ✗ Wrong: pick-up B (this will FAIL - B is not on table!)")

    beliefs_parts.append(f"\n=== PHYSICS CONSTRAINTS ===")
    beliefs_parts.append("1. You can only hold ONE block at a time")
    beliefs_parts.append("2. You can only pick up blocks that are CLEAR (nothing on top)")
    beliefs_parts.append("3. You can only stack on blocks that are CLEAR")
    beliefs_parts.append("4. pick-up ONLY works for blocks ON TABLE")
    beliefs_parts.append("5. unstack ONLY works for blocks ON OTHER BLOCKS")

    beliefs_parts.append(f"\n=== AVAILABLE ACTIONS ===")
    beliefs_parts.append("- pick-up X: Pick up block X from TABLE (X must be clear and ON TABLE)")
    beliefs_parts.append("- put-down X: Put block X on table (you must be holding X)")
    beliefs_parts.append("- stack X Y: Put block X on top of block Y (you hold X, Y must be clear)")
    beliefs_parts.append("- unstack X Y: Take block X off block Y (X must be clear, hand empty)")

    beliefs_parts.append(f"\n=== PLANNING REQUIREMENTS ===")
    beliefs_parts.append("Generate a SEQUENTIAL plan where each action depends on the previous one.")
    beliefs_parts.append("The plan graph must be CONNECTED - all actions form one chain/path.")

    beliefs = "\n".join(beliefs_parts)

    # --- TEARDOWN PHASE ---

    step_num = 1
    teardown_text = ""

    # Identify initial on-pairs that are NOT in the goal
    initial_pairs = [
        (top, bottom)
        for top, bottom in stacks.items()
        if (top, bottom) not in goal_pairs
    ]

    if initial_pairs:
        # Order by height (top-first) for safer unstacking
        heights = {}

        def get_height(b):
            if b in heights:
                return heights[b]
            if b in on_table:
                heights[b] = 0
                return 0
            if b in stacks:
                h = 1 + get_height(stacks[b])
                heights[b] = h
                return h
            return 0

        initial_pairs.sort(key=lambda pair: get_height(pair[0]), reverse=True)

        teardown_text += "Teardown steps (clearing mismatches):\n"
        for top, bottom in initial_pairs:
            teardown_text += (
                f"    Step {step_num}: unstack {top} from {bottom}, then put-down {top}\n"
            )
            step_num += 1
        teardown_text += "\n  "

    # --- END TEARDOWN PHASE ---

    # Build goal with bottom-up tower ordering and explicit construction steps

    # Build bottom-up ordering: find tower bases and walk upward
    # on_map: bottom_block -> block_that_goes_on_top
    on_map = {}
    top_set = set()
    bottom_set = set()
    for top_blk, bot_blk in list(goal_pairs):
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

    if teardown_text:
        goal_desc += f"\n  {teardown_text}"

    for tower in towers:
        goal_desc += f"\n  Tower (base={tower[0]}): {' -> '.join(tower)}  (bottom to top)\n"
        goal_desc += f"  Construction steps:\n"
        for i in range(1, len(tower)):
            blk = tower[i]
            tgt = tower[i - 1]
            goal_desc += f"    Step {step_num}: pick-up {blk}, then stack {blk} on {tgt}\n"
            step_num += 1

    goal_desc += "\n=== EXAMPLES ===\n"
    goal_desc += "\nExample 1 — Simple case (all blocks on table):\n"
    goal_desc += "  Initial: A, B, C all on table\n"
    goal_desc += "  Goal: Build tower C -> B -> A (C on table, B on C, A on B)\n"
    goal_desc += "  Plan: 1. pick-up B   2. stack B C   3. pick-up A   4. stack A B\n"

    goal_desc += "\nExample 2 — Complex case (initial stacks exist):\n"
    goal_desc += "  Initial: (on C B), (on B A), A on table  [tower: C-B-A]\n"
    goal_desc += "  Goal: (on A B), (on C A)  [tower: B-A-C]\n"
    goal_desc += "  Analysis: Need to dismantle C-B-A, then rebuild as B-A-C\n"
    goal_desc += "  Plan:\n"
    goal_desc += "    1. unstack C B  (now holding C)\n"
    goal_desc += "    2. put-down C   (C on table, hand empty)\n"
    goal_desc += "    3. unstack B A  (now holding B)\n"
    goal_desc += "    4. put-down B   (B on table, hand empty)\n"
    goal_desc += "    5. pick-up A    (now holding A)\n"
    goal_desc += "    6. stack A B    (A on B, hand empty)\n"
    goal_desc += "    7. pick-up C    (now holding C)\n"
    goal_desc += "    8. stack C A    (C on A, done!)\n"

    goal_desc += "\n⚠️  KEY INSIGHT: When blocks are already stacked, you MUST unstack them first!\n"
    goal_desc += "Work step-by-step, one action at a time. Each action depends on completing the previous action."

    desire = goal_desc

    return beliefs, desire

def pddl_to_nl_generic(pddl_data: dict) -> Tuple[str, str]:
    """Generic PDDL to NL conversion with complete state/goal preservation."""
    objects = pddl_data['objects']
    init = pddl_data['init']
    goal = pddl_data['goal']
    domain_name = pddl_data.get("domain_name", "unknown")

    beliefs_parts = [f"Domain: {domain_name}", "", "Objects:"]
    if objects:
        beliefs_parts.append("  " + ", ".join(objects))
    else:
        beliefs_parts.append("  (none)")
    beliefs_parts.append("")
    beliefs_parts.append("Initial state:")
    if init:
        for pred in init:
            beliefs_parts.append(f"  ({pred})")
    else:
        beliefs_parts.append("  (none)")

    desire_parts = ["Goal conditions:"]
    if goal:
        for pred in goal:
            desire_parts.append(f"  ({pred})")
    else:
        desire_parts.append("  (none parsed)")
    desire_parts.append("")
    desire_parts.append("Generate a sequential connected plan using ONLY actions defined in the domain.")

    beliefs = "\n".join(beliefs_parts)
    desire = "\n".join(desire_parts)
    return beliefs, desire

def pddl_to_nl_logistics(pddl_data: dict) -> Tuple[str, str]:
    """Logistics domain conversion with enhanced airport/city awareness"""
    objects = pddl_data['objects']
    init = pddl_data['init']
    goal = pddl_data['goal']

    # Parse logistics state comprehensively
    packages = []
    trucks = []
    airplanes = []
    airports = set()       # locations that are airports
    cities = []
    city_locations = {}    # city -> [locations]
    location_city = {}     # location -> city

    at_locations = {}  # object -> location
    in_vehicle = {}    # package -> vehicle

    for pred in init:
        parts = pred.split()
        if not parts:
            continue
        pred_name = parts[0].lower()

        if pred_name == 'at' and len(parts) >= 3:
            at_locations[parts[1]] = parts[2]
        elif pred_name == 'in' and len(parts) >= 3:
            in_vehicle[parts[1]] = parts[2]
        elif pred_name == 'airport' and len(parts) >= 2:
            airports.add(parts[1])
        elif pred_name == 'in-city' and len(parts) >= 3:
            loc, city = parts[1], parts[2]
            city_locations.setdefault(city, []).append(loc)
            location_city[loc] = city
        elif pred_name == 'obj' and len(parts) >= 2:
            packages.append(parts[1])
        elif pred_name == 'truck' and len(parts) >= 2:
            trucks.append(parts[1])
        elif pred_name == 'airplane' and len(parts) >= 2:
            airplanes.append(parts[1])
        elif pred_name == 'city' and len(parts) >= 2:
            cities.append(parts[1])

    # Build beliefs
    beliefs_parts = []
    beliefs_parts.append("LOGISTICS DOMAIN")

    # === WORLD STRUCTURE: Cities, Locations, Airports ===
    beliefs_parts.append("\n=== WORLD STRUCTURE ===")
    beliefs_parts.append(f"Cities: {', '.join(sorted(cities))}")
    for city in sorted(city_locations.keys()):
        locs = city_locations[city]
        airport_locs = sorted([l for l in locs if l in airports])
        non_airport_locs = sorted([l for l in locs if l not in airports])
        beliefs_parts.append(f"  {city}: AIRPORT(s)={airport_locs}, other locations={non_airport_locs}")

    beliefs_parts.append("")
    beliefs_parts.append(f"⚠️  AIRPORTS (airplanes can ONLY fly between these): {sorted(airports)}")
    beliefs_parts.append("   Non-airport locations CANNOT be used with fly-airplane!")

    # === VEHICLE POSITIONS ===
    beliefs_parts.append("\n=== VEHICLE POSITIONS ===")
    beliefs_parts.append("Airplanes (fly between AIRPORTS only):")
    for ap in sorted(airplanes):
        loc = at_locations.get(ap, "unknown")
        city = location_city.get(loc, "?")
        is_airport = "✓ AIRPORT" if loc in airports else "✗ NOT airport"
        beliefs_parts.append(f"  {ap} is at {loc} ({is_airport}, {city})")

    beliefs_parts.append("Trucks (drive within ONE city only):")
    for tr in sorted(trucks):
        loc = at_locations.get(tr, "unknown")
        city = location_city.get(loc, "?")
        beliefs_parts.append(f"  {tr} is at {loc} ({city})")

    # === PACKAGE POSITIONS ===
    beliefs_parts.append("\n=== PACKAGE POSITIONS ===")
    for pkg in sorted(packages):
        if pkg in in_vehicle:
            beliefs_parts.append(f"  {pkg} is IN {in_vehicle[pkg]}")
        elif pkg in at_locations:
            loc = at_locations[pkg]
            city = location_city.get(loc, "?")
            beliefs_parts.append(f"  {pkg} is at {loc} ({city})")

    # === ACTIONS ===
    beliefs_parts.append("\n=== AVAILABLE ACTIONS WITH EXACT PARAMETER FORMAT ===")
    beliefs_parts.append('1. load-truck: {"obj": "<package>", "truck": "<truck>", "loc": "<location>"}')
    beliefs_parts.append('2. unload-truck: {"obj": "<package>", "truck": "<truck>", "loc": "<location>"}')
    beliefs_parts.append('3. load-airplane: {"obj": "<package>", "airplane": "<airplane>", "loc": "<AIRPORT>"}')
    beliefs_parts.append('4. unload-airplane: {"obj": "<package>", "airplane": "<airplane>", "loc": "<AIRPORT>"}')
    beliefs_parts.append('5. drive-truck: {"truck": "<truck>", "from": "<loc>", "to": "<loc>", "city": "<city>"}')
    beliefs_parts.append('6. fly-airplane: {"airplane": "<airplane>", "from": "<AIRPORT>", "to": "<AIRPORT>"}')

    # === CRITICAL RULES ===
    beliefs_parts.append("\n=== CRITICAL RULES ===")
    beliefs_parts.append(f"⚠️  AIRPORTS in this problem: {sorted(airports)}")
    beliefs_parts.append("1. fly-airplane: BOTH 'from' and 'to' MUST be AIRPORT locations")
    beliefs_parts.append("   ❌ WRONG: fly-airplane with non-airport location")
    beliefs_parts.append("2. drive-truck: 'from' and 'to' MUST be in the SAME city")
    beliefs_parts.append("   ❌ WRONG: drive-truck between different cities")
    beliefs_parts.append("3. load/unload: vehicle and package MUST be at the SAME location")
    beliefs_parts.append("4. Inter-city transport pattern:")
    beliefs_parts.append("   truck→airport(load)→fly→airport(unload)→truck→destination")

    # === STATE TRACKING ===
    beliefs_parts.append("\n=== STATE TRACKING (MANDATORY) ===")
    beliefs_parts.append("After EVERY action, update your mental state table:")
    beliefs_parts.append("  - fly-airplane: airplane moves to destination AIRPORT")
    beliefs_parts.append("  - drive-truck: truck moves to destination location")
    beliefs_parts.append("  - load-*: package is IN vehicle, no longer at location")
    beliefs_parts.append("  - unload-*: package is AT location, no longer in vehicle")
    beliefs_parts.append("")
    beliefs_parts.append("BEFORE each action, verify:")
    beliefs_parts.append("  - Is the vehicle at the correct location RIGHT NOW?")
    beliefs_parts.append("  - Is the package at the correct location (for load)?")
    beliefs_parts.append("  - Is the package in the vehicle (for unload)?")
    beliefs_parts.append(f"  - For fly-airplane: is the location an AIRPORT? (only {sorted(airports)})")

    beliefs = "\n".join(beliefs_parts)

    # Build goal
    goal_descs = []
    for pred in goal:
        parts = pred.split()
        if parts[0] == 'at' and len(parts) >= 3:
            pkg, loc = parts[1], parts[2]
            city = location_city.get(loc, "?")
            # Determine if inter-city transport is needed
            pkg_loc = at_locations.get(pkg, "")
            pkg_city = location_city.get(pkg_loc, "?")
            if pkg_city != city and pkg_city != "?":
                goal_descs.append(f"{pkg} → {loc} ({city}) [currently in {pkg_city}, needs AIRPLANE]")
            else:
                goal_descs.append(f"{pkg} → {loc} ({city}) [same city, truck only]")

    desire_parts = []
    desire_parts.append(f"Goal: deliver {len(goal_descs)} package(s):")
    for gd in goal_descs:
        desire_parts.append(f"  - {gd}")

    desire_parts.append(f"\n⚠️  AIRPORTS: {sorted(airports)} — fly-airplane ONLY between these!")
    desire_parts.append("Track vehicle positions after EVERY action.")
    desire_parts.append("Generate a SEQUENTIAL plan with CONNECTED actions.")

    desire = "\n".join(desire_parts)

    return beliefs, desire

def pddl_to_nl_depots(pddl_data: dict) -> Tuple[str, str]:
    """Enhanced Depots domain conversion with clear action specifications"""
    objects = pddl_data['objects']
    typed_objects = pddl_data.get('typed_objects', )
    init = pddl_data['init']
    goal = pddl_data['goal']

    # Parse depots state
    crates = []
    trucks = []
    hoists = []
    pallets = []
    locations = []

    at_locations = {}  # object -> location
    on_surface = {}    # crate -> surface (pallet or crate)
    in_truck = {}      # crate -> truck
    lifting = {}       # hoist -> crate (if any)
    available = set()  # available hoists
    clear = set()      # clear surfaces

    for pred in init:
        parts = pred.split()
        if not parts:
            continue

        pred_name = parts[0]

        if pred_name == 'at' and len(parts) >= 3:
            at_locations[parts[1]] = parts[2]
        elif pred_name == 'on' and len(parts) >= 3:
            on_surface[parts[1]] = parts[2]
        elif pred_name == 'in' and len(parts) >= 3:
            in_truck[parts[1]] = parts[2]
        elif pred_name == 'lifting' and len(parts) >= 3:
            lifting[parts[1]] = parts[2]
        elif pred_name == 'available' and len(parts) >= 2:
            available.add(parts[1])
        elif pred_name == 'clear' and len(parts) >= 2:
            clear.add(parts[1])

    # Classify objects by type using typed_objects mapping
    for obj in objects:
        obj_type = typed_objects.get(obj, '').lower()
        if 'crate' in obj or obj_type == 'crate':
            crates.append(obj)
        elif 'truck' in obj or obj_type == 'truck':
            trucks.append(obj)
        elif 'hoist' in obj or obj_type == 'hoist':
            hoists.append(obj)
        elif 'pallet' in obj or obj_type == 'pallet':
            pallets.append(obj)
        elif 'depot' in obj or 'distributor' in obj or obj_type in ('depot', 'distributor', 'place'):
            locations.append(obj)

    # Build beliefs with detailed state description
    beliefs_parts = []
    beliefs_parts.append("DEPOTS DOMAIN")

    # List objects with types
    beliefs_parts.append("\n=== OBJECTS AND TYPES ===")
    if typed_objects:
        type_groups = {}
        for obj_name, obj_type in typed_objects.items():
            type_groups.setdefault(obj_type, []).append(obj_name)
        for type_name, obj_names in sorted(type_groups.items()):
            beliefs_parts.append(f"  {type_name}: {', '.join(sorted(obj_names))}")
    else:
        beliefs_parts.append(f"  Objects: {', '.join(objects[:30])}")

    beliefs_parts.append("\n=== CURRENT STATE ===")

    if at_locations:
        loc_descs = [f"{obj} is at {loc}" for obj, loc in list(at_locations.items())[:15]]
        beliefs_parts.append(f"\nLocations: {'; '.join(loc_descs)}")

    if on_surface:
        surface_descs = [f"{crate} is on {surf}" for crate, surf in list(on_surface.items())[:10]]
        beliefs_parts.append(f"On surfaces: {'; '.join(surface_descs)}")

    if in_truck:
        truck_descs = [f"{crate} is in {truck}" for crate, truck in list(in_truck.items())[:10]]
        beliefs_parts.append(f"In trucks: {'; '.join(truck_descs)}")

    if available:
        beliefs_parts.append(f"Available hoists: {', '.join(sorted(available))}")

    if clear:
        beliefs_parts.append(f"Clear surfaces: {', '.join(sorted(clear))}")

    beliefs_parts.append("\n=== AVAILABLE ACTIONS ===")
    beliefs_parts.append("⚠️  CRITICAL: Use ONLY these Depots actions. DO NOT use blocksworld actions!")
    beliefs_parts.append("⚠️  Parameter names MUST use the EXACT object names listed above (e.g., hoist0, crate0, pallet0, depot0)")
    beliefs_parts.append("")
    beliefs_parts.append("1. Lift <hoist> <crate> <surface> <place>")
    beliefs_parts.append("   - hoist: a Hoist object (e.g., hoist0)")
    beliefs_parts.append("   - crate: a Crate object (e.g., crate0)")
    beliefs_parts.append("   - surface: a Pallet or Crate the crate is ON (e.g., pallet0)")
    beliefs_parts.append("   - place: a Depot or Distributor location (e.g., depot0)")
    beliefs_parts.append("   - Preconditions: hoist available, crate on surface, crate clear, all at place")
    beliefs_parts.append("   - Effects: hoist lifting crate, crate no longer on surface, surface becomes clear")
    beliefs_parts.append("")
    beliefs_parts.append("2. Drop <hoist> <crate> <surface> <place>")
    beliefs_parts.append("   - hoist: a Hoist | crate: a Crate")
    beliefs_parts.append("   - surface: a Pallet or Crate to drop ONTO | place: a Depot or Distributor")
    beliefs_parts.append("   - Preconditions: hoist lifting crate, surface clear, all at place")
    beliefs_parts.append("   - Effects: crate on surface, hoist available, crate becomes clear")
    beliefs_parts.append("")
    beliefs_parts.append("3. Load <hoist> <crate> <truck> <place>")
    beliefs_parts.append("   - hoist: a Hoist | crate: a Crate | truck: a Truck | place: a Depot/Distributor")
    beliefs_parts.append("   - Preconditions: hoist lifting crate, truck at place, hoist at place")
    beliefs_parts.append("   - Effects: crate in truck, hoist available")
    beliefs_parts.append("")
    beliefs_parts.append("4. Unload <hoist> <crate> <truck> <place>")
    beliefs_parts.append("   - hoist: a Hoist | crate: a Crate | truck: a Truck | place: a Depot/Distributor")
    beliefs_parts.append("   - Preconditions: hoist available, crate in truck, truck at place, hoist at place")
    beliefs_parts.append("   - Effects: hoist lifting crate, crate no longer in truck")
    beliefs_parts.append("")
    beliefs_parts.append("5. Drive <truck> <from> <to>")
    beliefs_parts.append("   - truck: a Truck | from: a Depot/Distributor | to: a Depot/Distributor")
    beliefs_parts.append("   - Preconditions: truck at from location")
    beliefs_parts.append("   - Effects: truck at to location, no longer at from")

    beliefs_parts.append("\n=== CRITICAL RULES ===")
    beliefs_parts.append("❌ DO NOT use blocksworld actions: pick-up, put-down, stack, unstack")
    beliefs_parts.append("✓ ONLY use depots actions: Lift, Drop, Load, Unload, Drive")
    beliefs_parts.append("- Hoists are used to manipulate crates (like robotic arms)")
    beliefs_parts.append("- Crates can be on pallets or on other crates")
    beliefs_parts.append("- Trucks transport crates between locations")
    beliefs_parts.append("- All manipulation requires a hoist at the same location")
    beliefs_parts.append("- To move a crate to a different location: Lift -> Load -> Drive -> Unload -> Drop")
    beliefs_parts.append("- To rearrange crates at the SAME location: just Lift and Drop (no truck needed)")

    beliefs_parts.append("\n=== CRITICAL: HOIST STATE MACHINE ===")
    beliefs_parts.append("⚠️  A hoist has TWO states - you MUST track this:")
    beliefs_parts.append("")
    beliefs_parts.append("1. AVAILABLE: Can lift a crate")
    beliefs_parts.append("2. LIFTING <crate>: Holding a crate, CANNOT lift another crate")
    beliefs_parts.append("")
    beliefs_parts.append("State transitions:")
    beliefs_parts.append("  - Lift: available → lifting <crate>")
    beliefs_parts.append("  - Drop: lifting <crate> → available")
    beliefs_parts.append("  - Load: lifting <crate> → available (crate goes into truck)")
    beliefs_parts.append("  - Unload: available → lifting <crate> (crate comes out of truck)")
    beliefs_parts.append("")
    beliefs_parts.append("❌ WRONG: (Lift hoist0 crate1 ...) then (Lift hoist0 crate2 ...)")
    beliefs_parts.append("   → hoist0 is LIFTING crate1, cannot lift crate2!")
    beliefs_parts.append("")
    beliefs_parts.append("✓ RIGHT: (Lift hoist0 crate1 ...) then (Drop hoist0 crate1 ...) then (Lift hoist0 crate2 ...)")
    beliefs_parts.append("   → hoist0 becomes available after Drop")
    beliefs_parts.append("")
    beliefs_parts.append("✓ ALSO RIGHT: (Lift hoist0 crate1 ...) then (Load hoist0 crate1 truck0 ...)")
    beliefs_parts.append("   → hoist0 becomes available after Load")

    beliefs_parts.append("\n=== CRITICAL: TRUCK POSITION & CONTENTS TRACKING ===")
    beliefs_parts.append("⚠️  You MUST track truck positions and contents:")
    beliefs_parts.append("")
    beliefs_parts.append("1. TRUCK POSITION:")
    beliefs_parts.append("   - After Drive: truck is NOW at destination, NOT at origin")
    beliefs_parts.append("   - Example: (Drive truck0 depot0 depot1) → truck0 is now AT depot1")
    beliefs_parts.append("   - ❌ WRONG: Unload at old location after driving away")
    beliefs_parts.append("   - ✓ RIGHT: Only Load/Unload at truck's CURRENT location")
    beliefs_parts.append("")
    beliefs_parts.append("2. TRUCK CONTENTS:")
    beliefs_parts.append("   - After Load: crate is IN truck, NOT at location")
    beliefs_parts.append("   - After Unload: crate is being LIFTED by hoist, NOT in truck")
    beliefs_parts.append("   - Example: (Load hoist0 crate0 truck0 depot0) → crate0 is now IN truck0")
    beliefs_parts.append("   - ❌ WRONG: Unload a crate that was never loaded")
    beliefs_parts.append("   - ✓ RIGHT: Only unload crates that are IN the truck")

    beliefs_parts.append("\n=== BEFORE EACH ACTION, CHECK ===")
    beliefs_parts.append("1. Is the hoist AVAILABLE? (not lifting another crate)")
    beliefs_parts.append("2. Is the truck at the right location?")
    beliefs_parts.append("3. Is the crate at the expected location/surface?")
    beliefs_parts.append("4. For Unload: Is the crate IN the truck?")
    beliefs_parts.append("5. For Lift: Is the crate CLEAR (nothing on top)?")

    beliefs_parts.append("\n=== WORKED EXAMPLE WITH STATE TRACKING ===")
    beliefs_parts.append("Scenario: crate0 on pallet0 at depot0, crate1 on pallet1 at depot1")
    beliefs_parts.append("          truck0 at depot0, hoist0 at depot0, hoist1 at depot1")
    beliefs_parts.append("Goal: crate0 on crate1 at depot1")
    beliefs_parts.append("")
    beliefs_parts.append("Initial state:")
    beliefs_parts.append("  - hoist0: AVAILABLE at depot0")
    beliefs_parts.append("  - hoist1: AVAILABLE at depot1")
    beliefs_parts.append("  - truck0: at depot0, EMPTY")
    beliefs_parts.append("  - crate0: on pallet0 at depot0")
    beliefs_parts.append("")
    beliefs_parts.append("Step-by-step with state changes:")
    beliefs_parts.append("  1. Lift hoist0 crate0 pallet0 depot0")
    beliefs_parts.append("     → State: hoist0 is now LIFTING crate0 (not available!)")
    beliefs_parts.append("     → State: crate0 is now held by hoist0 (not on pallet0)")
    beliefs_parts.append("")
    beliefs_parts.append("  2. Load hoist0 crate0 truck0 depot0")
    beliefs_parts.append("     → State: hoist0 is now AVAILABLE (released crate0)")
    beliefs_parts.append("     → State: crate0 is now IN truck0 (not held by hoist)")
    beliefs_parts.append("     → State: truck0 contains crate0")
    beliefs_parts.append("")
    beliefs_parts.append("  3. Drive truck0 depot0 depot1")
    beliefs_parts.append("     → State: truck0 is now AT depot1 (not at depot0!)")
    beliefs_parts.append("     → State: truck0 still contains crate0")
    beliefs_parts.append("")
    beliefs_parts.append("  4. Unload hoist1 crate0 truck0 depot1")
    beliefs_parts.append("     → State: hoist1 is now LIFTING crate0 (not available!)")
    beliefs_parts.append("     → State: crate0 is now held by hoist1 (not in truck)")
    beliefs_parts.append("     → State: truck0 is now EMPTY")
    beliefs_parts.append("")
    beliefs_parts.append("  5. Drop hoist1 crate0 crate1 depot1")
    beliefs_parts.append("     → State: hoist1 is now AVAILABLE (released crate0)")
    beliefs_parts.append("     → State: crate0 is now ON crate1 at depot1 ✓ GOAL ACHIEVED")
    beliefs_parts.append("")
    beliefs_parts.append("⚠️  CRITICAL: Track hoist state! After Lift/Unload, hoist is LIFTING (not available).")
    beliefs_parts.append("⚠️  CRITICAL: Track truck position! After Drive, truck is at NEW location.")
    beliefs_parts.append("⚠️  CRITICAL: Track crate location! After Load, crate is IN truck (not at depot).")

    beliefs_parts.append("\n=== PLANNING REQUIREMENTS ===")
    beliefs_parts.append("Generate a SEQUENTIAL plan where each action depends on the previous one.")
    beliefs_parts.append("The plan graph must be CONNECTED - all actions form one chain/path.")
    beliefs_parts.append("Work step-by-step, one action at a time.")

    beliefs = "\n".join(beliefs_parts)

    # Build goal description
    goal_descs = []
    for pred in goal[:15]:
        parts = pred.split()
        if parts[0] == 'at' and len(parts) >= 3:
            goal_descs.append(f"{parts[1]} should be at {parts[2]}")
        elif parts[0] == 'on' and len(parts) >= 3:
            goal_descs.append(f"{parts[1]} should be on {parts[2]}")

    desire = f"Goal: {'; '.join(goal_descs)}. Use Depots actions (Lift/Drop/Load/Unload/Drive) to achieve this goal."

    return beliefs, desire

# ============================================================================
# BDI PLANNING
# ============================================================================

def _serialize_plan_nodes(plan: BDIPlan | None) -> List[Dict[str, object]]:
    """Serialize plan nodes into JSON-safe dicts."""
    if plan is None:
        return []
    return [
        {
            "id": node.id,
            "action_type": node.action_type,
            "params": dict(node.params),
            "description": node.description,
        }
        for node in plan.nodes
    ]


def _build_domain_runtime(
    domain: str,
    pddl_domain_path: str | None,
    beliefs: str,
    desire: str,
    instance_id: str | None,
    problem_objects: list[str] | None = None,
    typed_objects: dict[str, str] | None = None,
) -> dict:
    """Prepare reusable serializers and prompt context for one instance."""
    runtime = {
        "domain_context": "",
        "domain_spec": None,
        "generic_serializer": None,
        "generic_task": None,
        "allowed_objects": set(problem_objects or []),
        "typed_objects": {str(k): str(v).lower() for k, v in (typed_objects or {}).items()},
        "allowed_action_names": set(),
    }
    if not pddl_domain_path:
        return runtime

    domain_text = Path(pddl_domain_path).read_text()
    domain_spec = DomainSpec.from_pddl(domain, domain_text)
    param_order_map = {
        action["name"]: [param_name for param_name, _ptype in action["parameters"]]
        for action in extract_actions_from_pddl(domain_text)
    }
    runtime["domain_context"] = domain_spec.domain_context or ""
    runtime["domain_spec"] = domain_spec
    runtime["allowed_action_names"] = {str(name).lower() for name in domain_spec.valid_action_types}
    runtime["generic_serializer"] = PDDLPlanSerializer(param_order_map=param_order_map)
    runtime["generic_task"] = PlanningTask(
        task_id=instance_id or Path(pddl_domain_path).stem,
        domain_name=domain,
        beliefs=beliefs,
        desire=desire,
        domain_context=domain_spec.domain_context,
    )
    return runtime


def load_domain_pddl_for_prompt(pddl_domain_path: str) -> str:
    """Load a prompt-friendly domain context from a PDDL domain file."""
    domain_text = Path(pddl_domain_path).read_text()
    domain_name = Path(pddl_domain_path).stem
    spec = DomainSpec.from_pddl(domain_name, domain_text)
    return spec.domain_context or domain_text


def _plan_to_pddl_actions(plan: BDIPlan, domain: str, runtime: dict) -> List[str]:
    """Convert a BDI plan to PDDL actions using the best available serializer."""
    serializer = runtime.get("generic_serializer")
    task = runtime.get("generic_task")
    if serializer is not None and task is not None:
        return serializer.from_bdi_plan(plan, task)
    return bdi_to_pddl_actions(
        plan,
        domain=domain,
        allowed_objects=runtime.get("allowed_objects"),
        typed_objects=runtime.get("typed_objects"),
    )


def _normalise_baseline_action_lines(
    raw_text: str,
    domain: str,
    allowed_action_names: set[str] | None = None,
    allowed_objects: set[str] | None = None,
) -> List[str]:
    """Extract grounded PDDL action lines from raw model output."""
    content = str(raw_text or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:[a-zA-Z0-9_-]+)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    candidates = [line.strip() for line in content.splitlines() if line.strip()]
    actions: List[str] = []
    for line in candidates:
        if line[0].isdigit() and "." in line:
            line = line.split(".", 1)[1].strip()
        if line.startswith("-"):
            line = line[1:].strip()
        if line.startswith("(") and line.endswith(")"):
            actions.append(line)

    if not actions:
        actions = [match.group(0).strip() for match in re.finditer(r"\([^()\n]+\)", content)]

    normalised: List[str] = []
    for action in actions:
        inner = action.strip()[1:-1].strip()
        if not inner:
            continue
        parts = inner.split()
        action_name, *args = parts
        norm_action_name = str(action_name).strip().lower()
        if allowed_action_names and norm_action_name not in allowed_action_names:
            continue
        encoded_args = [encode_planbench_symbol(domain, arg) for arg in args]
        if allowed_objects:
            if any(arg not in allowed_objects for arg in encoded_args):
                continue
        normalised.append(f"({action_name} {' '.join(encoded_args)})".replace("  ", " ").strip())

    return normalised


def generate_baseline_plan(
    beliefs: str,
    desire: str,
    domain_context: str = "",
    domain: str = "blocksworld",
    allowed_action_names: set[str] | None = None,
    allowed_objects: set[str] | None = None,
) -> dict:
    """Generate a direct action-sequence baseline without BDI graph prompting."""
    configure_dspy()
    predictor = dspy.Predict(GenerateBaselineActionSequence)
    allowed_actions_text = ", ".join(sorted(allowed_action_names or []))
    allowed_objects_text = ", ".join(sorted(allowed_objects or []))
    output_rules = (
        "Output ONLY grounded PDDL actions, exactly one action per line. "
        "Do not output JSON, markdown fences, bullets, explanations, or commentary. "
        "Every line must start with '(' and end with ')'. "
        "Use only the allowed action names and allowed objects. "
        "If the domain is obfuscated, preserve the exact obfuscated action names. "
        "Do not invent object names. Output at least one action when a plan exists."
    )
    pred = predictor(
        beliefs=beliefs,
        desire=desire,
        domain_context=domain_context or "",
        allowed_actions=allowed_actions_text,
        allowed_objects=allowed_objects_text,
        output_rules=output_rules,
    )
    raw_output = getattr(pred, "plan_actions", "")
    actions = _normalise_baseline_action_lines(
        raw_output,
        domain,
        allowed_action_names=allowed_action_names,
        allowed_objects=allowed_objects,
    )
    return {
        "raw_output": raw_output,
        "plan_actions": actions,
    }


def _default_verification_layers() -> dict:
    return {
        "structural": {"valid": None, "errors": [], "hard_errors": [], "warnings": []},
        "symbolic": {"valid": None, "errors": []},
        "physics": {"valid": None, "errors": []},
    }


def _make_checkpoint_result(label: str) -> dict:
    return {
        "label": label,
        "execution_mode": label,
        "success": False,
        "raw_output": "",
        "plan_actions": [],
        "pddl_actions": [],
        "plan_nodes": [],
        "verification_layers": _default_verification_layers(),
        "auto_repair": {"triggered": False, "success": False, "repairs_applied": []},
        "val_repair": {"attempts": 0, "success": False, "history": []},
        "symbolic_valid": False,
    }


def _evaluate_plan_actions(
    plan_actions: List[str],
    *,
    domain: str,
    pddl_problem_path: str | None,
    pddl_domain_path: str | None,
    init_state: Dict | None,
    structural: dict | None = None,
) -> dict:
    """Evaluate one checkpoint and return verifier outputs with success=VAL."""
    from bdi_llm.symbolic_verifier import BlocksworldPhysicsValidator, PDDLSymbolicVerifier

    layers = _default_verification_layers()
    if structural is not None:
        layers["structural"] = structural

    symbolic_valid = False
    symbolic_errors: List[str] = []
    if pddl_problem_path and pddl_domain_path:
        verifier = PDDLSymbolicVerifier()
        symbolic_valid, symbolic_errors = verifier.verify_plan(
            domain_file=pddl_domain_path,
            problem_file=pddl_problem_path,
            plan_actions=plan_actions,
            verbose=True,
        )
    else:
        symbolic_errors = ["Skipped - Missing PDDL files"]
    layers["symbolic"] = {"valid": symbolic_valid, "errors": symbolic_errors}

    physics_valid = None
    physics_errors: List[str] = []
    if init_state is not None and domain == "blocksworld":
        physics_validator = BlocksworldPhysicsValidator()
        physics_valid, physics_errors = physics_validator.validate_plan(plan_actions, init_state)
    elif init_state is not None:
        physics_valid = True
        physics_errors = ["Skipped - No physics validator for this domain"]
    layers["physics"] = {"valid": physics_valid, "errors": physics_errors}

    return {
        "verification_layers": layers,
        "symbolic_valid": bool(symbolic_valid),
        "success": bool(symbolic_valid),
    }


def _evaluate_bdi_plan_checkpoint(
    plan: BDIPlan,
    *,
    planner: BDIPlanner,
    beliefs: str,
    desire: str,
    domain: str,
    pddl_problem_path: str | None,
    pddl_domain_path: str | None,
    init_state: Dict | None,
    runtime: dict,
    instance_id: str | None,
    allow_structural_auto_repair: bool,
    allow_val_repair: bool,
) -> dict:
    """Evaluate a BDI-generated plan with optional structural and VAL repair."""
    from bdi_llm.symbolic_verifier import IntegratedVerifier, PDDLSymbolicVerifier

    current_plan = plan
    result = _make_checkpoint_result("bdi")

    graph = current_plan.to_networkx()
    struct_result = PlanVerifier.verify(graph)
    structural = {
        "valid": struct_result.is_valid,
        "errors": struct_result.errors,
        "hard_errors": struct_result.hard_errors,
        "warnings": struct_result.warnings,
    }

    if not struct_result.is_valid and allow_structural_auto_repair:
        result["auto_repair"]["triggered"] = True
        repaired_plan, repaired_valid, messages = repair_and_verify(current_plan)
        result["auto_repair"]["repairs_applied"] = messages
        if repaired_valid:
            current_plan = repaired_plan
            result["auto_repair"]["success"] = True
            graph = current_plan.to_networkx()
            struct_result = PlanVerifier.verify(graph)
            structural = {
                "valid": struct_result.is_valid,
                "errors": struct_result.errors,
                "hard_errors": struct_result.hard_errors,
                "warnings": struct_result.warnings,
            }

    plan_actions = _plan_to_pddl_actions(current_plan, domain, runtime)
    evaluation = _evaluate_plan_actions(
        plan_actions,
        domain=domain,
        pddl_problem_path=pddl_problem_path,
        pddl_domain_path=pddl_domain_path,
        init_state=init_state,
        structural=structural,
    )

    result.update(evaluation)
    result["plan_actions"] = plan_actions
    result["pddl_actions"] = plan_actions
    result["plan_nodes"] = _serialize_plan_nodes(current_plan)

    if allow_val_repair and not result["symbolic_valid"]:
        verifier = PDDLSymbolicVerifier()
        val_errors = result["verification_layers"]["symbolic"]["errors"]
        cumulative_history: List[dict] = []
        max_val_repairs = 5
        for repair_attempt in range(1, max_val_repairs + 1):
            clean_errors = [
                err for err in val_errors
                if not str(err).lstrip().startswith("Full VAL output:")
                and not str(err).lstrip().startswith("\nFull VAL output:")
            ]
            result["val_repair"]["attempts"] = repair_attempt
            result["val_repair"]["history"].append({
                "attempt": repair_attempt,
                "errors": clean_errors[:5],
                "repaired": False,
            })
            cumulative_history.append({
                "attempt": repair_attempt,
                "plan_actions": plan_actions,
                "val_errors": clean_errors,
            })

            verification_context = {
                "layers": {
                    "structural": {
                        "valid": result["verification_layers"]["structural"]["valid"],
                        "errors": result["verification_layers"]["structural"]["errors"],
                    },
                    "symbolic": {
                        "valid": False,
                        "errors": clean_errors,
                    },
                },
                "overall_valid": False,
            }
            failed_layers = [
                name for name, layer in verification_context["layers"].items()
                if not layer.get("valid", False)
            ]
            verification_context["error_summary"] = (
                f"Failed layers: {', '.join(failed_layers)}" if failed_layers else "All layers passed"
            )
            verification_feedback = IntegratedVerifier.build_planner_feedback(verification_context)

            repair_result = planner.repair_from_val_errors(
                beliefs=beliefs,
                desire=desire,
                previous_plan_actions=plan_actions,
                val_errors=clean_errors,
                repair_history=cumulative_history,
                verification_feedback=verification_feedback,
                instance_id=instance_id,
                domain=domain,
                domain_context=runtime.get("domain_context") or "",
                allow_early_exit=False,
            )
            current_plan = repair_result.plan
            plan_actions = _plan_to_pddl_actions(current_plan, domain, runtime)
            val_valid, val_errors = verifier.verify_plan(
                domain_file=pddl_domain_path,
                problem_file=pddl_problem_path,
                plan_actions=plan_actions,
                verbose=True,
            )

            graph = current_plan.to_networkx()
            struct_result = PlanVerifier.verify(graph)
            result["verification_layers"]["structural"] = {
                "valid": struct_result.is_valid,
                "errors": struct_result.errors,
                "hard_errors": struct_result.hard_errors,
                "warnings": struct_result.warnings,
            }
            result["verification_layers"]["symbolic"] = {"valid": val_valid, "errors": val_errors}
            result["plan_actions"] = plan_actions
            result["pddl_actions"] = plan_actions
            result["plan_nodes"] = _serialize_plan_nodes(current_plan)
            result["symbolic_valid"] = bool(val_valid)
            result["success"] = bool(val_valid)

            if val_valid:
                result["val_repair"]["success"] = True
                result["val_repair"]["history"][-1]["repaired"] = True
                break

    return result


def run_planbench_pipeline_for_instance(
    beliefs: str,
    desire: str,
    *,
    domain: str,
    pddl_problem_path: str | None,
    pddl_domain_path: str | None,
    init_state: Dict | None,
    objects: list[str] | None,
    typed_objects: dict[str, str] | None,
    execution_mode: str,
    instance_id: str | None,
) -> dict:
    """Run baseline -> bdi -> bdi_repair checkpoints for one instance."""
    mode_flags = execution_mode_flags(execution_mode)
    runtime = _build_domain_runtime(
        domain,
        pddl_domain_path,
        beliefs,
        desire,
        instance_id,
        problem_objects=objects,
        typed_objects=typed_objects,
    )

    baseline_raw = generate_baseline_plan(
        beliefs=beliefs,
        desire=desire,
        domain_context=runtime.get("domain_context") or "",
        domain=domain,
        allowed_action_names=runtime.get("allowed_action_names"),
        allowed_objects=runtime.get("allowed_objects"),
    )
    baseline_result = _make_checkpoint_result("baseline")
    baseline_result["raw_output"] = baseline_raw["raw_output"]
    baseline_result["plan_actions"] = baseline_raw["plan_actions"]
    baseline_result["pddl_actions"] = baseline_raw["plan_actions"]
    baseline_result.update(
        _evaluate_plan_actions(
            baseline_raw["plan_actions"],
            domain=domain,
            pddl_problem_path=pddl_problem_path,
            pddl_domain_path=pddl_domain_path,
            init_state=init_state,
            structural=None,
        )
    )

    pipeline = {
        "baseline_result": baseline_result,
        "bdi_initial_result": None,
        "bdi_repair_result": None,
    }

    if not mode_flags["run_bdi"]:
        return pipeline

    if runtime.get("domain_spec") is not None:
        planner = BDIPlanner(auto_repair=False, domain_spec=runtime["domain_spec"])
    else:
        planner = BDIPlanner(auto_repair=False, domain=domain)

    initial_pred = planner.generate_plan(
        beliefs=beliefs,
        desire=desire,
        domain_context=runtime.get("domain_context") or None,
    )
    planner.record_generation_trace(initial_pred)
    initial_plan = initial_pred.plan
    bdi_initial_result = _evaluate_bdi_plan_checkpoint(
        initial_plan,
        planner=planner,
        beliefs=beliefs,
        desire=desire,
        domain=domain,
        pddl_problem_path=pddl_problem_path,
        pddl_domain_path=pddl_domain_path,
        init_state=init_state,
        runtime=runtime,
        instance_id=instance_id,
        allow_structural_auto_repair=False,
        allow_val_repair=False,
    )
    pipeline["bdi_initial_result"] = bdi_initial_result

    if not mode_flags["run_bdi_repair"]:
        return pipeline

    if bdi_initial_result["success"]:
        repaired_result = json.loads(json.dumps(bdi_initial_result))
        repaired_result["label"] = "bdi_repair"
        repaired_result["execution_mode"] = "bdi_repair"
        repaired_result["repair_attempted"] = False
        pipeline["bdi_repair_result"] = repaired_result
        return pipeline

    if runtime.get("domain_spec") is not None:
        repair_planner = BDIPlanner(auto_repair=True, domain_spec=runtime["domain_spec"])
    else:
        repair_planner = BDIPlanner(auto_repair=True, domain=domain)

    repair_result = _evaluate_bdi_plan_checkpoint(
        initial_plan,
        planner=repair_planner,
        beliefs=beliefs,
        desire=desire,
        domain=domain,
        pddl_problem_path=pddl_problem_path,
        pddl_domain_path=pddl_domain_path,
        init_state=init_state,
        runtime=runtime,
        instance_id=instance_id,
        allow_structural_auto_repair=True,
        allow_val_repair=True,
    )
    repair_result["label"] = "bdi_repair"
    repair_result["execution_mode"] = "bdi_repair"
    repair_result["repair_attempted"] = True
    pipeline["bdi_repair_result"] = repair_result
    return pipeline

def bdi_to_pddl_actions(
    plan: BDIPlan,
    domain: str = "blocksworld",
    allowed_objects: set[str] | None = None,
    typed_objects: dict[str, str] | None = None,
) -> List[str]:
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

        # Logistics
        if t == "loadtruck": return "load-truck"
        if t == "unloadtruck": return "unload-truck"
        if t == "loadairplane": return "load-airplane"
        if t == "unloadairplane": return "unload-airplane"
        if t == "drivetruck": return "drive-truck"
        if t == "flyairplane": return "fly-airplane"

        return t

    allowed_objects_set = {str(obj).lower() for obj in (allowed_objects or [])}
    typed_objects_map = {str(k).lower(): str(v).lower() for k, v in (typed_objects or {}).items()}

    # Normalise parameters
    def _normalise_param(val: str) -> str:
        if not val:
            return ""
        s = str(val).lower().strip()
        # Remove "block " prefix if present (common LLM artifact)
        if s.startswith("block "):
            s = s[6:].strip()
        s = s.replace('"', '').replace("'", "")
        s = re.sub(r'\.replace\(.*$', '', s)
        s = re.sub(r'_fixme$', '', s)
        s = re.sub(r'[^a-z0-9_\-\s]', '', s)
        s = re.sub(r'\s+', ' ', s).strip()
        return s

    def _candidate_pool(expected_types: set[str] | None = None) -> list[str]:
        if not allowed_objects_set:
            return []
        if not expected_types or not typed_objects_map:
            return sorted(allowed_objects_set)
        pool = [obj for obj in allowed_objects_set if typed_objects_map.get(obj) in expected_types]
        return sorted(pool) if pool else sorted(allowed_objects_set)

    def _resolve_object(raw: str, expected_types: set[str] | None = None, description: str = "") -> str:
        token = _normalise_param(raw)
        if not token:
            return ""
        if not allowed_objects_set:
            return token
        if token in allowed_objects_set:
            return token

        compact = token.replace(' ', '')
        if compact in allowed_objects_set:
            return compact

        pool = _candidate_pool(expected_types)

        description_l = description.lower()
        description_hits = [candidate for candidate in pool if candidate in description_l]
        if len(description_hits) == 1:
            return description_hits[0]

        prefix_matches = [candidate for candidate in pool if candidate.startswith(compact)]
        if len(prefix_matches) == 1:
            return prefix_matches[0]

        try:
            import difflib
            match = difflib.get_close_matches(compact, pool, n=1, cutoff=0.75)
            if match:
                return match[0]
        except Exception:
            pass

        return ""

    def _pick_param(params: Dict, keys: List[str]) -> str:
        for key in keys:
            value = params.get(key)
            if value:
                return _normalise_param(value)
        return ""

    # Convert each action to PDDL format using params deterministically
    for node_id in ordered_nodes:
        action_node = node_lookup.get(node_id)
        if not action_node:
            continue

        if (
            isinstance(action_node.action_type, str)
            and action_node.action_type.strip().startswith("(")
            and action_node.action_type.strip().endswith(")")
            and not action_node.params
        ):
            pddl_actions.append(action_node.action_type.strip())
            continue

        canon = _normalise(action_node.action_type)
        params = action_node.params
        before_len = len(pddl_actions)

        if domain == "blocksworld":
            block = _pick_param(params, ["block", "object", "obj", "x"]) \
                or _normalise_param(next(iter(params.values()), ""))
            target = _pick_param(params, ["target", "y", "to", "on"]) \
                or _normalise_param(next(iter(list(params.values())[1:]), ""))

            if canon == "pick-up" and block:
                pddl_actions.append(f"(pick-up {block})")
            elif canon == "put-down" and block:
                pddl_actions.append(f"(put-down {block})")
            elif canon == "stack" and block and target:
                pddl_actions.append(f"(stack {block} {target})")
            elif canon == "unstack" and block and target:
                pddl_actions.append(f"(unstack {block} {target})")

        elif domain == "logistics":
            # Enhanced parameter extraction with more variations and fallbacks
            # Try multiple parameter name variations
            obj = _pick_param(params, ["obj", "object", "package", "pkg", "p", "item", "package_name", "obj_name"])
            truck = _pick_param(params, ["truck", "vehicle", "t", "truck_name", "veh"])
            airplane = _pick_param(params, ["airplane", "plane", "a", "airplane_name", "aircraft"])
            loc = _pick_param(params, ["loc", "location", "l", "at", "place", "loc_name", "location_name"])
            loc_from = _pick_param(params, ["from", "source", "origin", "loc_from", "from_loc", "start"])
            loc_to = _pick_param(params, ["to", "dest", "destination", "target", "loc_to", "to_loc", "end"])
            city = _pick_param(params, ["city", "c", "city_name"])

            # Fallback: try to extract from description if parameters are missing
            description = action_node.description.lower() if hasattr(action_node, 'description') and action_node.description else ""

            # Fallback: use positional parameters if named parameters fail
            param_values = list(params.values())

            if canon == "load-truck":
                if not obj and len(param_values) >= 1:
                    obj = _normalise_param(param_values[0])
                if not truck and len(param_values) >= 2:
                    truck = _normalise_param(param_values[1])
                if not loc and len(param_values) >= 3:
                    loc = _normalise_param(param_values[2])

                if obj and truck and loc:
                    pddl_actions.append(f"(LOAD-TRUCK {obj} {truck} {loc})")
                else:
                    print(f"    DEBUG: load-truck missing params - obj={obj}, truck={truck}, loc={loc}, params={params}")

            elif canon == "load-airplane":
                if not obj and len(param_values) >= 1:
                    obj = _normalise_param(param_values[0])
                if not airplane and len(param_values) >= 2:
                    airplane = _normalise_param(param_values[1])
                if not loc and len(param_values) >= 3:
                    loc = _normalise_param(param_values[2])

                if obj and airplane and loc:
                    pddl_actions.append(f"(LOAD-AIRPLANE {obj} {airplane} {loc})")
                else:
                    print(f"    DEBUG: load-airplane missing params - obj={obj}, airplane={airplane}, loc={loc}, params={params}")

            elif canon == "unload-truck":
                if not obj and len(param_values) >= 1:
                    obj = _normalise_param(param_values[0])
                if not truck and len(param_values) >= 2:
                    truck = _normalise_param(param_values[1])
                if not loc and len(param_values) >= 3:
                    loc = _normalise_param(param_values[2])

                if obj and truck and loc:
                    pddl_actions.append(f"(UNLOAD-TRUCK {obj} {truck} {loc})")
                else:
                    print(f"    DEBUG: unload-truck missing params - obj={obj}, truck={truck}, loc={loc}, params={params}")

            elif canon == "unload-airplane":
                if not obj and len(param_values) >= 1:
                    obj = _normalise_param(param_values[0])
                if not airplane and len(param_values) >= 2:
                    airplane = _normalise_param(param_values[1])
                if not loc and len(param_values) >= 3:
                    loc = _normalise_param(param_values[2])

                if obj and airplane and loc:
                    pddl_actions.append(f"(UNLOAD-AIRPLANE {obj} {airplane} {loc})")
                else:
                    print(f"    DEBUG: unload-airplane missing params - obj={obj}, airplane={airplane}, loc={loc}, params={params}")

            elif canon == "drive-truck":
                if not truck and len(param_values) >= 1:
                    truck = _normalise_param(param_values[0])
                if not loc_from and len(param_values) >= 2:
                    loc_from = _normalise_param(param_values[1])
                if not loc_to and len(param_values) >= 3:
                    loc_to = _normalise_param(param_values[2])
                if not city and len(param_values) >= 4:
                    city = _normalise_param(param_values[3])

                if truck and loc_from and loc_to and city:
                    pddl_actions.append(f"(DRIVE-TRUCK {truck} {loc_from} {loc_to} {city})")
                else:
                    print(f"    DEBUG: drive-truck missing params - truck={truck}, from={loc_from}, to={loc_to}, city={city}, params={params}")

            elif canon == "fly-airplane":
                if not airplane and len(param_values) >= 1:
                    airplane = _normalise_param(param_values[0])
                if not loc_from and len(param_values) >= 2:
                    loc_from = _normalise_param(param_values[1])
                if not loc_to and len(param_values) >= 3:
                    loc_to = _normalise_param(param_values[2])

                if airplane and loc_from and loc_to:
                    pddl_actions.append(f"(FLY-AIRPLANE {airplane} {loc_from} {loc_to})")
                else:
                    print(f"    DEBUG: fly-airplane missing params - airplane={airplane}, from={loc_from}, to={loc_to}, params={params}")

        elif domain == "depots":
            # Depots combines logistics and blocksworld
            # Actions: Drive, Lift, Drop, Load, Unload
            # Domain PDDL signature reference:
            #   Drive(?x - truck ?y - place ?z - place)
            #   Lift(?x - hoist ?y - crate ?z - surface ?p - place)
            #   Drop(?x - hoist ?y - crate ?z - surface ?p - place)
            #   Load(?x - hoist ?y - crate ?z - truck ?p - place)
            #   Unload(?x - hoist ?y - crate ?z - truck ?p - place)
            hoist = _pick_param(params, [
                "hoist", "h", "x", "hoist_name", "lifter",
            ])
            crate = _pick_param(params, [
                "crate", "c", "obj", "object", "y", "item", "package",
                "crate_name", "cargo", "box",
            ])
            truck = _pick_param(params, [
                "truck", "t", "vehicle", "z", "truck_name", "veh",
            ])
            surface = _pick_param(params, [
                "surface", "s", "pallet", "z", "on", "target", "dest",
                "surface_name", "onto", "below", "under",
            ])
            loc = _pick_param(params, [
                "loc", "location", "place", "p", "at", "depot",
                "loc_name", "location_name", "position", "area",
            ])
            loc_from = _pick_param(params, [
                "from", "loc_from", "from_loc", "from_location",
                "source", "origin", "start", "y",
            ])
            loc_to = _pick_param(params, [
                "to", "loc_to", "to_loc", "to_location",
                "dest", "destination", "target", "end", "z",
            ])

            # Positional fallback using param_values
            param_values = list(params.values())
            description = action_node.description.lower() if getattr(action_node, 'description', None) else ""

            if canon == "drive":
                # Drive(?x - truck ?y - place ?z - place)
                if not truck and len(param_values) >= 1:
                    truck = _normalise_param(param_values[0])
                if not loc_from and len(param_values) >= 2:
                    loc_from = _normalise_param(param_values[1])
                if not loc_to and len(param_values) >= 3:
                    loc_to = _normalise_param(param_values[2])

                truck = _resolve_object(truck, {"truck"}, description)
                loc_from = _resolve_object(loc_from, {"depot", "distributor", "place"}, description)
                loc_to = _resolve_object(loc_to, {"depot", "distributor", "place"}, description)

                if truck and loc_from and loc_to:
                    pddl_actions.append(f"(Drive {truck} {loc_from} {loc_to})")
                else:
                    print(f"    DEBUG: drive missing params - truck={truck}, from={loc_from}, to={loc_to}, params={params}")

            elif canon == "lift":
                # Lift(?x - hoist ?y - crate ?z - surface ?p - place)
                if not hoist and len(param_values) >= 1:
                    hoist = _normalise_param(param_values[0])
                if not crate and len(param_values) >= 2:
                    crate = _normalise_param(param_values[1])
                if not surface and len(param_values) >= 3:
                    surface = _normalise_param(param_values[2])
                if not loc and len(param_values) >= 4:
                    loc = _normalise_param(param_values[3])

                hoist = _resolve_object(hoist, {"hoist"}, description)
                crate = _resolve_object(crate, {"crate"}, description)
                surface = _resolve_object(surface, {"crate", "pallet", "surface"}, description)
                loc = _resolve_object(loc, {"depot", "distributor", "place"}, description)

                if hoist and crate and surface and loc:
                    pddl_actions.append(f"(Lift {hoist} {crate} {surface} {loc})")
                else:
                    print(f"    DEBUG: lift missing params - hoist={hoist}, crate={crate}, surface={surface}, loc={loc}, params={params}")

            elif canon == "drop":
                # Drop(?x - hoist ?y - crate ?z - surface ?p - place)
                if not hoist and len(param_values) >= 1:
                    hoist = _normalise_param(param_values[0])
                if not crate and len(param_values) >= 2:
                    crate = _normalise_param(param_values[1])
                if not surface and len(param_values) >= 3:
                    surface = _normalise_param(param_values[2])
                if not loc and len(param_values) >= 4:
                    loc = _normalise_param(param_values[3])

                hoist = _resolve_object(hoist, {"hoist"}, description)
                crate = _resolve_object(crate, {"crate"}, description)
                surface = _resolve_object(surface, {"crate", "pallet", "surface"}, description)
                loc = _resolve_object(loc, {"depot", "distributor", "place"}, description)

                if hoist and crate and surface and loc:
                    pddl_actions.append(f"(Drop {hoist} {crate} {surface} {loc})")
                else:
                    print(f"    DEBUG: drop missing params - hoist={hoist}, crate={crate}, surface={surface}, loc={loc}, params={params}")

            elif canon == "load":
                # Load(?x - hoist ?y - crate ?z - truck ?p - place)
                if not hoist and len(param_values) >= 1:
                    hoist = _normalise_param(param_values[0])
                if not crate and len(param_values) >= 2:
                    crate = _normalise_param(param_values[1])
                if not truck and len(param_values) >= 3:
                    truck = _normalise_param(param_values[2])
                if not loc and len(param_values) >= 4:
                    loc = _normalise_param(param_values[3])

                hoist = _resolve_object(hoist, {"hoist"}, description)
                crate = _resolve_object(crate, {"crate"}, description)
                truck = _resolve_object(truck, {"truck"}, description)
                loc = _resolve_object(loc, {"depot", "distributor", "place"}, description)

                if hoist and crate and truck and loc:
                    pddl_actions.append(f"(Load {hoist} {crate} {truck} {loc})")
                else:
                    print(f"    DEBUG: load missing params - hoist={hoist}, crate={crate}, truck={truck}, loc={loc}, params={params}")

            elif canon == "unload":
                # Unload(?x - hoist ?y - crate ?z - truck ?p - place)
                if not hoist and len(param_values) >= 1:
                    hoist = _normalise_param(param_values[0])
                if not crate and len(param_values) >= 2:
                    crate = _normalise_param(param_values[1])
                if not truck and len(param_values) >= 3:
                    truck = _normalise_param(param_values[2])
                if not loc and len(param_values) >= 4:
                    loc = _normalise_param(param_values[3])

                hoist = _resolve_object(hoist, {"hoist"}, description)
                crate = _resolve_object(crate, {"crate"}, description)
                truck = _resolve_object(truck, {"truck"}, description)
                loc = _resolve_object(loc, {"depot", "distributor", "place"}, description)

                if hoist and crate and truck and loc:
                    pddl_actions.append(f"(Unload {hoist} {crate} {truck} {loc})")
                else:
                    print(f"    DEBUG: unload missing params - hoist={hoist}, crate={crate}, truck={truck}, loc={loc}, params={params}")

        if len(pddl_actions) == before_len:
            print(
                f"    ⚠️  WARNING: Skipped action '{action_node.action_type}' (canon: {canon}) with params {params} for domain '{domain}'"
            )

    return pddl_actions

def generate_bdi_plan(
    beliefs: str,
    desire: str,
    pddl_problem_path: str = None,  # NEW: Path to problem file for VAL
    pddl_domain_path: str = None,   # NEW: Path to domain file for VAL
    init_state: Dict = None,
    domain: str = "blocksworld",
    timeout: int = 60,
    auto_repair: bool = True,
    max_retries: int = 3,
    execution_mode: str | None = None,
    instance_id: Optional[str] = None,  # NEW: Unique instance identifier for budget tracking
) -> Tuple[BDIPlan, bool, dict]:
    """
    Generate plan with BDI-LLM and multi-layer verification

    Args:
        beliefs: Natural language beliefs
        desire: Natural language goal
        pddl_problem_path: Path to PDDL problem file (for symbolic verification)
        pddl_domain_path: Path to PDDL domain file (for symbolic verification)
        init_state: Initial state for physics validation (optional)
        domain: PDDL domain name (default: blocksworld)
        timeout: Planning timeout
        auto_repair: Enable automatic plan repair (default: True)
        max_retries: Maximum retries for API errors (default: 3)

    Returns:
        (plan, is_valid, metrics)
    """
    from bdi_llm.symbolic_verifier import (
        BlocksworldPhysicsValidator,
        IntegratedVerifier,
        PDDLSymbolicVerifier,
    )

    start_time = time.time()
    resolved_mode = resolve_execution_mode(execution_mode)
    mode_flags = execution_mode_flags(resolved_mode)
    metrics = {
        'execution_mode': resolved_mode,
        'generation_time': 0,
        'verification_layers': {
            'structural': {'valid': False, 'errors': [], 'hard_errors': [], 'warnings': []},
            'symbolic': {'valid': False, 'errors': []},  # VAL verification
            'physics': {'valid': False, 'errors': []}
        },
        'auto_repair': {
            'triggered': False,
            'success': False,
            'repairs_applied': []
        },
        'val_repair': {
            'attempts': 0,
            'success': False,
            'history': []  # List of {attempt, errors, repaired}
        },
        'overall_valid': False,
        'num_nodes': 0,
        'num_edges': 0,
        'retries': 0,
        'pddl_actions': [],
        'plan_nodes': [],
    }
    if Config.SAVE_REASONING_TRACE:
        metrics['reasoning_trace'] = {
            'enabled': True,
            'max_chars': Config.REASONING_TRACE_MAX_CHARS,
            'generation': None,
            'repairs': [],
        }

    last_error = None
    for attempt in range(max_retries):
        try:
            generic_domain = domain not in BUILTIN_PLAN_DOMAINS
            domain_context = None
            generic_serializer = None
            generic_task = None

            if generic_domain:
                if not pddl_domain_path:
                    raise ValueError(
                        "Generic PDDL planning requires pddl_domain_path for action schema extraction."
                    )
                domain_text = Path(pddl_domain_path).read_text()
                domain_spec = DomainSpec.from_pddl(domain, domain_text)
                param_order_map = {
                    action["name"]: [param_name for param_name, _ptype in action["parameters"]]
                    for action in extract_actions_from_pddl(domain_text)
                }
                generic_serializer = PDDLPlanSerializer(param_order_map=param_order_map)
                generic_task = PlanningTask(
                    task_id=instance_id or Path(pddl_problem_path or "generic").stem,
                    domain_name=domain,
                    beliefs=beliefs,
                    desire=desire,
                    domain_context=domain_spec.domain_context,
                )
                domain_context = load_domain_pddl_for_prompt(pddl_domain_path)
                planner = BDIPlanner(auto_repair=auto_repair, domain_spec=domain_spec)
            else:
                planner = BDIPlanner(auto_repair=auto_repair, domain=domain)

            def plan_to_pddl_actions(plan_obj: BDIPlan) -> List[str]:
                if generic_serializer is not None and generic_task is not None:
                    return generic_serializer.from_bdi_plan(plan_obj, generic_task)
                return bdi_to_pddl_actions(plan_obj, domain=domain)

            result = planner.generate_plan(
                beliefs=beliefs,
                desire=desire,
                domain_context=domain_context,
            )
            planner.record_generation_trace(result)
            plan = result.plan
            metrics['plan_nodes'] = _serialize_plan_nodes(plan)
            metrics['pddl_actions'] = plan_to_pddl_actions(plan)
            metrics['retries'] = attempt
            if Config.SAVE_REASONING_TRACE:
                metrics['reasoning_trace']['generation'] = planner.get_last_generation_trace()

            metrics['generation_time'] = time.time() - start_time

            # Layer 1: Structural verification
            G = plan.to_networkx()
            struct_result = PlanVerifier.verify(G)
            struct_valid = struct_result.is_valid
            struct_errors = struct_result.errors
            struct_hard_errors = struct_result.hard_errors
            struct_warnings = struct_result.warnings

            # If structural verification fails and auto_repair is enabled at this level too
            if not struct_valid and auto_repair and mode_flags['structural_auto_repair']:
                metrics['auto_repair']['triggered'] = True
                repaired_plan, repaired_valid, messages = repair_and_verify(plan)
                if repaired_valid:
                    plan = repaired_plan
                    G = plan.to_networkx()
                    struct_result = PlanVerifier.verify(G)
                    struct_valid = struct_result.is_valid
                    struct_errors = struct_result.errors
                    struct_hard_errors = struct_result.hard_errors
                    struct_warnings = struct_result.warnings
                    metrics['auto_repair']['success'] = True
                    metrics['auto_repair']['repairs_applied'] = messages

            metrics['verification_layers']['structural']['valid'] = struct_valid
            metrics['verification_layers']['structural']['errors'] = struct_errors
            metrics['verification_layers']['structural']['hard_errors'] = struct_hard_errors
            metrics['verification_layers']['structural']['warnings'] = struct_warnings
            metrics['num_nodes'] = len(plan.nodes)
            metrics['num_edges'] = len(plan.edges)

            # Layer 2: Symbolic Verification (PDDL/VAL) with repair loop
            symbolic_valid = True
            symbolic_errors = [f"Skipped - execution mode: {resolved_mode}"]
            max_val_repairs = 5

            if mode_flags['symbolic_check']:
                symbolic_valid = False
                symbolic_errors = ["Skipped - Structural failure"]

                # VAL is the ultimate validator - if VAL says plan works, it works.
                # Even if structural verification fails, we should still try VAL.
                # Set still_try_val to True to let VAL check even structurally failed plans.
                still_try_val = not struct_valid  # Key fix: try VAL even if structural fails
                if still_try_val:
                    print(f"    Structural verification failed, but still attempting VAL verification")
            else:
                still_try_val = False

            if mode_flags['symbolic_check'] and (struct_valid or still_try_val) and pddl_problem_path and pddl_domain_path:
                try:
                    # Convert BDI plan to PDDL actions
                    pddl_actions = plan_to_pddl_actions(plan)
                    metrics['pddl_actions'] = pddl_actions

                    # Initialize VAL verifier
                    val_verifier = PDDLSymbolicVerifier()
                    symbolic_valid, symbolic_errors = val_verifier.verify_plan(
                        domain_file=pddl_domain_path,
                        problem_file=pddl_problem_path,
                        plan_actions=pddl_actions,
                        verbose=True
                    )

                    # VAL error-driven repair loop (with cumulative history)
                    val_repair_attempt = 0
                    cumulative_repair_history = []  # Accumulate all previous attempts
                    while mode_flags['val_repair'] and not symbolic_valid and val_repair_attempt < max_val_repairs:
                        val_repair_attempt += 1
                        metrics['val_repair']['attempts'] = val_repair_attempt

                        # Filter out verbose full VAL output — only keep
                        # specific error messages and repair advice for the LLM
                        clean_errors = [
                            e for e in symbolic_errors
                            if not e.lstrip().startswith("Full VAL output:")
                            and not e.lstrip().startswith("\nFull VAL output:")
                        ]

                        metrics['val_repair']['history'].append({
                            'attempt': val_repair_attempt,
                            'errors': clean_errors[:5],  # Limit stored errors
                            'repaired': False
                        })

                        # Record current failed attempt before repair (clean errors only)
                        cumulative_repair_history.append({
                            'attempt': val_repair_attempt,
                            'plan_actions': pddl_actions,
                            'val_errors': clean_errors,
                        })

                        try:
                            print(f"    VAL repair attempt {val_repair_attempt}/{max_val_repairs} - errors: {clean_errors[:2]}")

                            verification_context = {
                                'layers': {
                                    'structural': {
                                        'valid': struct_valid,
                                        'errors': struct_errors,
                                    },
                                    'symbolic': {
                                        'valid': symbolic_valid,
                                        'errors': clean_errors,
                                    },
                                },
                                'overall_valid': struct_valid and symbolic_valid,
                            }
                            failed_layers = [
                                name
                                for name, layer in verification_context['layers'].items()
                                if not layer.get('valid', False)
                            ]
                            verification_context['error_summary'] = (
                                f"Failed layers: {', '.join(failed_layers)}"
                                if failed_layers
                                else "All layers passed"
                            )
                            verification_feedback = IntegratedVerifier.build_planner_feedback(
                                verification_context
                            )

                            # Call LLM to repair based on VAL errors + full history
                            repair_result = planner.repair_from_val_errors(
                                beliefs=beliefs,
                                desire=desire,
                                previous_plan_actions=pddl_actions,
                                val_errors=clean_errors,
                                repair_history=cumulative_repair_history,
                                verification_feedback=verification_feedback,
                                instance_id=instance_id,  # For budget tracking
                                domain=domain,  # For cache keying
                                domain_context=domain_context,
                                allow_early_exit=False,
                            )
                            if Config.SAVE_REASONING_TRACE:
                                repair_trace = planner.get_last_repair_trace()
                                if repair_trace:
                                    repair_trace['attempt'] = val_repair_attempt
                                    metrics['reasoning_trace']['repairs'].append(repair_trace)
                            plan = repair_result.plan

                            # Re-verify structure after repair
                            G = plan.to_networkx()
                            struct_result_r = PlanVerifier.verify(G)
                            struct_valid_r = struct_result_r.is_valid
                            struct_errors_r = struct_result_r.errors

                            # KEY INSIGHT: VAL is the ultimate validator.
                            # If structural check fails but VAL passes, the plan works.
                            # Don't break - let VAL verify anyway.
                            if not struct_valid_r:
                                print(f"    VAL repair {val_repair_attempt}: structural failure after repair, but still trying VAL")
                                struct_valid = struct_valid_r  # Update for outer scope
                            else:
                                struct_valid = struct_valid_r  # Update for outer scope
                            struct_errors = struct_errors_r

                            # Re-convert and re-verify with VAL (even if structural fails)
                            pddl_actions = plan_to_pddl_actions(plan)
                            symbolic_valid, symbolic_errors = val_verifier.verify_plan(
                                domain_file=pddl_domain_path,
                                problem_file=pddl_problem_path,
                                plan_actions=pddl_actions,
                                verbose=True
                            )

                            if symbolic_valid:
                                metrics['val_repair']['success'] = True
                                metrics['val_repair']['history'][-1]['repaired'] = True
                                # Update structural metrics with repaired plan
                                metrics['num_nodes'] = len(plan.nodes)
                                metrics['num_edges'] = len(plan.edges)
                                print(f"    VAL repair {val_repair_attempt}: SUCCESS")

                        except Exception as repair_err:
                            print(f"    VAL repair {val_repair_attempt} failed: {str(repair_err)[:100]}")
                            continue

                except Exception as e:
                    symbolic_valid = False
                    symbolic_errors = [f"Symbolic verification error: {str(e)}"]
            else:
                if mode_flags['symbolic_check']:
                    # No VAL verification because PDDL files are missing
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
            physics_errors = [f"Skipped - execution mode: {resolved_mode}"]

            if mode_flags['physics_check'] and init_state is not None and struct_valid:
                # Validate physics (only for blocksworld domain)
                if domain == "blocksworld":
                    pddl_actions = plan_to_pddl_actions(plan)
                    metrics['pddl_actions'] = pddl_actions
                    physics_validator = BlocksworldPhysicsValidator()
                    physics_valid, physics_errors = physics_validator.validate_plan(
                        pddl_actions, init_state
                    )
                elif domain != "blocksworld":
                    # Skip physics validation for non-blocksworld domains
                    physics_valid = True
                    physics_errors = ["Skipped - No physics validator for this domain"]

            metrics['verification_layers']['physics']['valid'] = physics_valid
            metrics['verification_layers']['physics']['errors'] = physics_errors

            # Overall validation:
            # KEY PRINCIPLE: VAL is the ultimate validator - if VAL says plan works, it works.
            # A plan that passes VAL is considered valid even with minor structural issues.
            # Structural validation is a heuristic; VAL's symbolic execution is ground truth.
            if mode_flags['symbolic_check'] and symbolic_valid and pddl_problem_path and pddl_domain_path:
                # VAL passed = plan works (regardless of structural status)
                overall_valid = True
                print(f"    Overall: VALID (VAL passed, structural={struct_valid}, physics={physics_valid})")
            else:
                # No VAL verification available - fall back to local layers only.
                overall_valid = struct_valid and (physics_valid if mode_flags['physics_check'] else True)
                print(
                    f"    Overall: {'VALID' if overall_valid else 'INVALID'} "
                    f"(mode={resolved_mode}, structural={struct_valid}, physics={physics_valid})"
                )

            metrics['overall_valid'] = overall_valid
            metrics['plan_nodes'] = _serialize_plan_nodes(plan)

            return plan, overall_valid, metrics

        except Exception as e:
            last_error = str(e)
            metrics['retries'] = attempt + 1

            # Check if it's a retryable error (connection issues, rate limits)
            error_str = str(e).lower()
            if ('connection' in error_str or 'timeout' in error_str or 'internal' in error_str
                or 'resourceexhausted' in error_str or '429' in error_str
                or 'rate' in error_str or 'quota' in error_str):
                if attempt < max_retries - 1:
                    import time as time_module
                    wait_time = 2 ** (attempt + 1)  # Exponential backoff
                    print(f"    API error, retrying in {wait_time}s... ({attempt + 1}/{max_retries})")
                    time_module.sleep(wait_time)
                    continue

            # Non-retryable error or max retries reached
            metrics['generation_time'] = time.time() - start_time
            metrics['verification_layers']['structural']['errors'] = [last_error]
            metrics['verification_layers']['structural']['hard_errors'] = [last_error]
            metrics['verification_layers']['structural']['warnings'] = []

            # Return empty plan
            plan = BDIPlan(goal_description=desire, nodes=[], edges=[])
            metrics['plan_nodes'] = []
            return plan, False, metrics

    # Should not reach here, but just in case
    metrics['generation_time'] = time.time() - start_time
    metrics['verification_layers']['structural']['errors'] = [f"Max retries ({max_retries}) exceeded: {last_error}"]
    metrics['verification_layers']['structural']['hard_errors'] = [f"Max retries ({max_retries}) exceeded: {last_error}"]
    metrics['verification_layers']['structural']['warnings'] = []
    plan = BDIPlan(goal_description=desire, nodes=[], edges=[])
    metrics['plan_nodes'] = []
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

def save_checkpoint_atomic(results: dict, checkpoint_file: str) -> None:
    """Persist checkpoint atomically to reduce corruption risk on interruption."""
    tmp_file = f"{checkpoint_file}.tmp"
    with open(tmp_file, 'w') as f:
        json.dump(results, f, indent=2)
    os.replace(tmp_file, checkpoint_file)

def evaluate_single_instance(instance_file: str, domain: str, execution_mode: str | None = None) -> dict:
    """
    Evaluate a single PDDL instance.

    Args:
        instance_file: Path to PDDL problem file
        domain: Domain name (blocksworld, depots, logistics)

    Returns:
        Dictionary with evaluation results
    """
    instance_result = {
        'instance_file': instance_file,
        'instance_name': Path(instance_file).stem,
        'timestamp': datetime.now().isoformat(),
        'execution_mode': resolve_execution_mode(execution_mode),
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

        pipeline_results = run_planbench_pipeline_for_instance(
            beliefs=beliefs,
            desire=desire,
            domain=domain,
            pddl_problem_path=instance_file,
            pddl_domain_path=domain_file,
            init_state=init_state,
            objects=pddl_data.get('objects', []),
            typed_objects=pddl_data.get('typed_objects', {}),
            execution_mode=instance_result['execution_mode'],
            instance_id=instance_file,  # Use instance file path as unique ID
        )

        instance_result.update(pipeline_results)
        selected_key = stage_result_key(instance_result['execution_mode'])
        selected_result = instance_result.get(selected_key) or {}
        instance_result['bdi_metrics'] = selected_result  # legacy alias
        instance_result['success'] = bool(selected_result.get('success', False))

    except Exception as e:
        instance_result['success'] = False
        instance_result['error'] = str(e)

    return instance_result

def run_batch_evaluation(
    domain: str,
    max_instances: int = None,
    resume_from: str = None,
    output_dir: str = "runs/planbench_results",
    parallel: bool = False,
    max_workers: int = 200,
    instances_file: str = None,
    checkpoint_every: int = 1,
    execution_mode: str | None = None,
) -> dict:
    """Run evaluation on all instances in a domain with MLflow tracking"""
    global MLFLOW_AVAILABLE

    print(f"\n{'='*80}")
    print(f"  PLANBENCH FULL EVALUATION: {domain}")
    print(f"{'='*80}\n")

    resolved_mode = resolve_execution_mode(execution_mode)

    # Setup
    base_path = PLANBENCH_ROOT
    os.makedirs(output_dir, exist_ok=True)

    # Find instances
    if instances_file:
        # Load instances from file
        print(f"Loading instances from: {instances_file}")
        with open(instances_file, 'r') as f:
            instances = [line.strip() for line in f if line.strip()]
        print(f"Loaded {len(instances)} instances from file")
    else:
        # Find all instances in domain
        instances = find_all_instances(base_path, domain)
        if max_instances:
            instances = instances[:max_instances]
        print(f"Found {len(instances)} instances")

    checkpoint_file = checkpoint_path(output_dir, domain, resolved_mode)
    effective_resume = resume_from
    if effective_resume is None and os.path.exists(checkpoint_file):
        effective_resume = checkpoint_file
        print(f"Auto-resume enabled from latest checkpoint: {effective_resume}")
    elif effective_resume and not os.path.exists(effective_resume):
        print(f"⚠️  Resume file not found: {effective_resume}")
        effective_resume = None

    if checkpoint_every < 1:
        checkpoint_every = 1

    # Initialize MLflow tracking
    mlflow_run_id = None
    if MLFLOW_AVAILABLE:
        try:
            # Set experiment name based on domain
            mlflow.set_experiment(f"planbench-{domain}")

            # Start MLflow run with descriptive name
            run_name = f"{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            mlflow.start_run(run_name=run_name)
            mlflow_run_id = mlflow.active_run().info.run_id

            # Log parameters
            mlflow.log_param("domain", domain)
            mlflow.log_param("execution_mode", resolved_mode)
            mlflow.log_param("max_instances", max_instances if max_instances else "all")
            mlflow.log_param("total_instances", len(instances))
            mlflow.log_param("resume_from", effective_resume if effective_resume else "none")
            mlflow.log_param("checkpoint_every", checkpoint_every)
            mlflow.log_param("model", "claude-opus-4")
            mlflow.log_param("auto_repair", True)

            print(f"✓ MLflow tracking enabled (Run ID: {mlflow_run_id})")
        except Exception as e:
            print(f"⚠️  MLflow initialization failed: {e}")
            print("   Continuing without MLflow tracking...")
            MLFLOW_AVAILABLE = False

    selected_result_key = stage_result_key(resolved_mode)

    # Load checkpoint if resuming
    completed = set()
    results = {
        'domain': domain,
        'execution_mode': resolved_mode,
        'timestamp': datetime.now().isoformat(),
        'total_instances': len(instances),
        'results': []
    }

    if effective_resume and os.path.exists(effective_resume):
        print(f"Resuming from checkpoint: {effective_resume}")
        with open(effective_resume, 'r') as f:
            checkpoint = json.load(f)
            results['results'] = checkpoint.get('results', [])
            completed = {
                r['instance_file']
                for r in results['results']
                if r.get(selected_result_key) is not None
            }
        print(f"Skipping {len(completed)} completed instances")

    # Evaluate each instance
    # Initialize counters from resumed results (if any), then accumulate new ones.
    success_count = sum(1 for r in results['results'] if r.get('success', False))
    failed_count = len(results['results']) - success_count
    results_lock = Lock()  # Thread-safe results collection

    # Filter out completed instances
    instances_to_process = [inst for inst in instances if inst not in completed]

    if parallel and max_workers > 1:
        # Parallel execution mode
        print(f"Running in parallel mode with {max_workers} workers")

        # Rate limiting: limit concurrent API calls to max_workers
        import threading
        api_semaphore = threading.Semaphore(max_workers)

        def rate_limited_evaluate(instance_file, domain):
            with api_semaphore:
                return evaluate_single_instance(instance_file, domain, resolved_mode)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_instance = {
                executor.submit(rate_limited_evaluate, instance_file, domain): instance_file
                for instance_file in instances_to_process
            }

            # Process completed tasks with progress bar
            with tqdm(total=len(instances_to_process), desc=f"Evaluating {domain}") as pbar:
                for future in as_completed(future_to_instance):
                    try:
                        instance_result = future.result(timeout=300)  # 5 minute timeout
                    except TimeoutError:
                        instance_file = future_to_instance[future]
                        instance_result = {
                            'instance_file': instance_file,
                            'instance_name': Path(instance_file).stem,
                            'success': False,
                            'error': 'Timeout after 300 seconds',
                            'bdi_metrics': {
                                'overall_valid': False,
                                'verification_layers': {
                                    'structural': {
                                        'valid': False,
                                        'errors': ['Timeout after 300 seconds'],
                                        'hard_errors': ['Timeout after 300 seconds'],
                                        'warnings': []
                                    },
                                    'symbolic': {'valid': False, 'errors': []},
                                    'physics': {'valid': False, 'errors': []}
                                }
                            }
                        }

                    # Thread-safe result collection
                    with results_lock:
                        results['results'].append(instance_result)

                        if instance_result.get('success', False):
                            success_count += 1
                        else:
                            failed_count += 1

                        # Save checkpoint at configured interval
                        if len(results['results']) % checkpoint_every == 0:
                            save_checkpoint_atomic(results, checkpoint_file)

                    pbar.update(1)
    else:
        # Serial execution mode (original behavior)
        for instance_file in tqdm(instances_to_process, desc=f"Evaluating {domain}"):
            instance_result = evaluate_single_instance(instance_file, domain, resolved_mode)

            results['results'].append(instance_result)

            if instance_result.get('success', False):
                success_count += 1
            else:
                failed_count += 1

            # Save checkpoint at configured interval
            if len(results['results']) % checkpoint_every == 0:
                save_checkpoint_atomic(results, checkpoint_file)

    # Always persist latest progress snapshot
    save_checkpoint_atomic(results, checkpoint_file)

    def _checkpoint_stats(result_key: str) -> dict:
        attempted = [r for r in results['results'] if r.get(result_key) is not None]
        success = sum(1 for r in attempted if r.get(result_key, {}).get('success', False))
        return {
            'attempted': len(attempted),
            'success_count': success,
            'success_rate': success / len(attempted) if attempted else 0,
        }

    baseline_stats = _checkpoint_stats('baseline_result')
    bdi_stats = _checkpoint_stats('bdi_initial_result')
    bdi_repair_stats = _checkpoint_stats('bdi_repair_result')

    repair_contribution = sum(
        1
        for r in results['results']
        if r.get('bdi_initial_result') is not None
        and r.get('bdi_repair_result') is not None
        and not r.get('bdi_initial_result', {}).get('success', False)
        and r.get('bdi_repair_result', {}).get('success', False)
    )

    val_repair_triggered = sum(
        1 for r in results['results']
        if (r.get('bdi_repair_result') or {}).get('val_repair', {}).get('attempts', 0) > 0
    )
    val_repair_success = sum(
        1 for r in results['results']
        if (r.get('bdi_repair_result') or {}).get('val_repair', {}).get('success', False)
    )
    val_repair_total_attempts = sum(
        (r.get('bdi_repair_result') or {}).get('val_repair', {}).get('attempts', 0)
        for r in results['results']
    )

    selected_stats = {
        'baseline': baseline_stats,
        'bdi': bdi_stats,
        'bdi-repair': bdi_repair_stats,
    }[resolved_mode]

    results['summary'] = {
        'total_evaluated': len(results['results']),
        'stage': resolved_mode,
        'success_count': selected_stats['success_count'],
        'failed_count': selected_stats['attempted'] - selected_stats['success_count'],
        'success_rate': selected_stats['success_rate'],
        'baseline': baseline_stats,
        'bdi': bdi_stats,
        'bdi_repair': bdi_repair_stats,
        'repair_contribution': {
            'successful_repairs': repair_contribution,
        },
        'val_repair': {
            'triggered': val_repair_triggered,
            'successful': val_repair_success,
            'total_attempts': val_repair_total_attempts,
            'success_rate': val_repair_success / val_repair_triggered if val_repair_triggered > 0 else 0,
        },
    }

    # Save final results
    output_file = f"{output_dir}/results_{domain}_{resolved_mode}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)

    # Log metrics and artifacts to MLflow
    if MLFLOW_AVAILABLE and mlflow_run_id:
        try:
            summary = results['summary']

            # Log aggregate metrics
            mlflow.log_metric("success_rate", summary['success_rate'])
            mlflow.log_metric("success_count", summary['success_count'])
            mlflow.log_metric("failed_count", summary['failed_count'])
            mlflow.log_metric("baseline_success_rate", summary['baseline']['success_rate'])
            mlflow.log_metric("bdi_success_rate", summary['bdi']['success_rate'])
            mlflow.log_metric("bdi_repair_success_rate", summary['bdi_repair']['success_rate'])
            mlflow.log_metric("repair_contribution", summary['repair_contribution']['successful_repairs'])

            mlflow.log_metric("val_repair_triggered", summary['val_repair']['triggered'])
            mlflow.log_metric("val_repair_successful", summary['val_repair']['successful'])
            mlflow.log_metric("val_repair_total_attempts", summary['val_repair']['total_attempts'])
            mlflow.log_metric("val_repair_success_rate", summary['val_repair']['success_rate'])

            # Log results file as artifact
            mlflow.log_artifact(output_file)

            print(f"✓ Metrics and artifacts logged to MLflow")
            print(f"  View at: http://localhost:5000/#/experiments/{mlflow.active_run().info.experiment_id}/runs/{mlflow_run_id}")

        except Exception as e:
            print(f"⚠️  MLflow logging failed: {e}")
        finally:
            # End MLflow run
            mlflow.end_run()

    print(f"\n{'='*80}")
    print(f"  EVALUATION COMPLETE")
    print(f"{'='*80}")
    print(f"\nDomain: {domain}")
    print(f"Stage: {resolved_mode}")
    print(f"Total instances: {len(results['results'])}")
    print(f"\n--- Checkpoint Success ---")
    print(f"baseline: {baseline_stats['success_count']}/{baseline_stats['attempted']} ({baseline_stats['success_rate']*100:.1f}%)")
    print(f"bdi: {bdi_stats['success_count']}/{bdi_stats['attempted']} ({bdi_stats['success_rate']*100:.1f}%)")
    print(f"bdi_repair: {bdi_repair_stats['success_count']}/{bdi_repair_stats['attempted']} ({bdi_repair_stats['success_rate']*100:.1f}%)")
    print(f"Repair contribution inside bdi_repair: {repair_contribution}")
    print(f"\n--- VAL Repair Loop Statistics ---")
    print(f"VAL repair triggered: {val_repair_triggered}")
    print(f"VAL repair successful: {val_repair_success}")
    print(f"VAL repair total attempts: {val_repair_total_attempts}")
    if val_repair_triggered > 0:
        print(f"VAL repair success rate: {val_repair_success/val_repair_triggered*100:.1f}%")
    print(f"\nSelected stage success: {selected_stats['success_count']}/{selected_stats['attempted']} ({selected_stats['success_rate']*100:.1f}%)")
    print(f"\nResults saved to: {output_file}")

    return results

# ============================================================================
# MAIN
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="PlanBench Full Benchmark Evaluation")
    parser.add_argument("--domain", type=str,
                       choices=[
                           "blocksworld",
                           "logistics",
                           "depots",
                           "obfuscated_deceptive_logistics",
                           "obfuscated_randomized_logistics",
                       ],
                       help="Domain to evaluate")
    parser.add_argument("--all_domains", action="store_true",
                       help="Evaluate all domains")
    parser.add_argument("--max_instances", type=int, default=None,
                       help="Maximum number of instances per domain (default: all)")
    parser.add_argument("--resume", type=str, default=None,
                       help="Resume from checkpoint file")
    parser.add_argument("--output_dir", type=str, default="runs/planbench_results",
                       help="Output directory for results")
    parser.add_argument("--parallel", action="store_true",
                       help="Enable parallel execution")
    parser.add_argument("--workers", type=int, default=200,
                       help="Number of parallel workers (default: 200)")
    parser.add_argument("--instances", type=str, default=None,
                       help="File containing list of instance paths to evaluate (one per line)")
    parser.add_argument("--checkpoint_every", type=int, default=1,
                       help="Save checkpoint every N completed instances (default: 1)")
    parser.add_argument("--execution_mode", type=str, default="bdi-repair",
                       choices=["baseline", "bdi", "bdi-repair"],
                       help="Run pipeline up to this checkpoint (default: bdi-repair)")

    args = parser.parse_args()

    # Check API credentials using project config resolution (supports .env + fallback aliases)
    credentials = Config.get_credentials()
    if not any(credentials.values()):
        print("❌ ERROR: No API credential set")
        print("   export OPENAI_API_KEY=your-key")
        print("   OR export ANTHROPIC_API_KEY=your-key")
        print("   OR export GOOGLE_API_KEY=your-key")
        print("   OR export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json")
        sys.exit(1)

    # Determine domains to evaluate
    if args.all_domains:
        domains = [
            "blocksworld",
            "depots",
            "logistics",
            "obfuscated_deceptive_logistics",
            "obfuscated_randomized_logistics",
        ]
    elif args.domain:
        domains = [args.domain]
    else:
        print("❌ ERROR: Must specify --domain or --all_domains")
        sys.exit(1)

    # Set execution mode for the current benchmark stage
    os.environ['AGENT_EXECUTION_MODE'] = args.execution_mode
    print(f"AGENT_EXECUTION_MODE={args.execution_mode}")

    # Run evaluation
    all_results = {}
    for domain in domains:
        results = run_batch_evaluation(
            domain=domain,
            max_instances=args.max_instances,
            resume_from=args.resume,
            output_dir=args.output_dir,
            parallel=args.parallel,
            max_workers=args.workers,
            instances_file=args.instances,
            checkpoint_every=args.checkpoint_every,
            execution_mode=args.execution_mode,
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
