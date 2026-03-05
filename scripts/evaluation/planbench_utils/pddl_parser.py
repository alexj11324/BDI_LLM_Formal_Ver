"""
PDDL Parsing Utilities
======================

Functions for parsing PDDL problem files, resolving domain files,
and finding PlanBench instances.
"""
import re
from pathlib import Path
from typing import List


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
        base_path = str(Path(__file__).resolve().parent.parent.parent / "workspaces/planbench_data/plan-bench")

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
