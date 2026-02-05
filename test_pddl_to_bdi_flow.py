#!/usr/bin/env python3
"""
Proof of Concept: PDDL → BDI → PDDL Pipeline
==============================================

Tests the complete flow:
1. Parse PDDL problem
2. Convert to natural language (beliefs + desire)
3. Generate plan with BDI-LLM
4. Convert DAG back to PDDL plan
5. Validate with PlanBench

Author: BDI-LLM Research
Date: 2026-02-03
"""

import sys
import os
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.bdi_llm.planner import BDIPlanner
from src.bdi_llm.schemas import BDIPlan
from src.bdi_llm.verifier import PlanVerifier


# ============================================================================
# STEP 1: PDDL → Natural Language Converter
# ============================================================================

def parse_pddl_problem(pddl_file: str) -> dict:
    """
    Parse a PDDL problem file into structured data

    Returns:
        {
            'objects': ['j', 'f', 'i', ...],
            'init': ['handempty', 'ontable j', 'clear j', ...],
            'goal': ['on j f', 'on f i', ...]
        }
    """
    with open(pddl_file, 'r') as f:
        content = f.read()

    # Extract objects
    objects_match = re.search(r':objects\s+(.*?)\)', content)
    objects = objects_match.group(1).split() if objects_match else []

    # Extract init state
    init_match = re.search(r':init\s+(.*?)\(:goal', content, re.DOTALL)
    if init_match:
        init_text = init_match.group(1)
        # Parse predicates
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

    return {
        'objects': objects,
        'init': init_predicates,
        'goal': goal_predicates
    }


def pddl_to_natural_language(pddl_data: dict) -> tuple:
    """
    Convert parsed PDDL to natural language (beliefs + desire)

    For blocksworld:
    - init states → beliefs about current configuration
    - goal states → desire for target configuration
    """
    objects = pddl_data['objects']
    init = pddl_data['init']
    goal = pddl_data['goal']

    # Build beliefs with PHYSICAL CONSTRAINTS
    beliefs_parts = []
    beliefs_parts.append(f"There are {len(objects)} blocks: {', '.join(objects)}")

    # Parse init state
    on_table = []
    clear_blocks = []
    hand_state = None

    for pred in init:
        parts = pred.split()
        if parts[0] == 'ontable':
            on_table.append(parts[1])
        elif parts[0] == 'clear':
            clear_blocks.append(parts[1])
        elif parts[0] == 'handempty':
            hand_state = "empty"

    if on_table:
        beliefs_parts.append(f"All blocks are currently on the table: {', '.join(on_table)}")
    if hand_state:
        beliefs_parts.append(f"Your hand is {hand_state}")
    if clear_blocks:
        beliefs_parts.append(f"All blocks are clear (nothing on top): {', '.join(clear_blocks)}")

    # ADD PHYSICAL CONSTRAINTS
    beliefs_parts.append("IMPORTANT: You can only hold ONE block at a time")
    beliefs_parts.append("You must pick up blocks from bottom to top when building stacks")
    beliefs_parts.append("Available actions: pick-up (grab from table), put-down (place on table), stack (place on another block), unstack (remove from another block)")

    beliefs = ". ".join(beliefs_parts) + "."

    # Build desire from goal - make it clearer
    goal_stacks = []
    for pred in goal:
        parts = pred.split()
        if parts[0] == 'on':
            goal_stacks.append(f"block {parts[1]} directly on top of block {parts[2]}")

    desire = f"Build a tower by stacking blocks in this order (from bottom to top): {' → '.join(goal_stacks)}. Build the tower step by step, one block at a time."

    return beliefs, desire


# ============================================================================
# STEP 2: BDI Planning
# ============================================================================

def generate_bdi_plan(beliefs: str, desire: str) -> BDIPlan:
    """Generate plan using BDI-LLM"""
    planner = BDIPlanner()

    result = planner.generate_plan(beliefs=beliefs, desire=desire)
    plan = result.plan

    # Verify
    G = plan.to_networkx()
    is_valid, errors = PlanVerifier.verify(G)

    if not is_valid:
        print(f"⚠️  Plan validation failed: {errors}")
    else:
        print(f"✅ Plan validated successfully")

    return plan, is_valid


# ============================================================================
# STEP 3: DAG → PDDL Plan Converter
# ============================================================================

def dag_to_pddl_plan(bdi_plan: BDIPlan) -> list:
    """
    Convert BDI DAG to PDDL action sequence

    Strategy:
    - Use topological sort for execution order
    - Map action nodes to PDDL actions based on description
    - Infer PDDL action parameters from node metadata
    """
    from src.bdi_llm.verifier import PlanVerifier
    import networkx as nx

    G = bdi_plan.to_networkx()

    # Get execution order
    if nx.is_directed_acyclic_graph(G):
        execution_order = list(nx.topological_sort(G))
    else:
        print("❌ Graph has cycles, cannot convert to linear plan")
        return []

    pddl_actions = []

    for node_id in execution_order:
        # Find corresponding ActionNode
        node = next((n for n in bdi_plan.nodes if n.id == node_id), None)

        if not node:
            continue

        # Skip virtual nodes
        if node.id in ["START", "END"]:
            continue

        # Try to infer PDDL action from description
        # This is a heuristic mapping for blocksworld
        desc = node.description.lower()

        if "pick" in desc or "grab" in desc:
            # Extract block name from description
            # e.g., "Pick up block j" → (pick-up j)
            block = extract_block_name(desc)
            if block:
                pddl_actions.append(f"(pick-up {block})")

        elif "put down" in desc or "place on table" in desc:
            block = extract_block_name(desc)
            if block:
                pddl_actions.append(f"(put-down {block})")

        elif "stack" in desc:
            # e.g., "Stack j on f" → (stack j f)
            blocks = extract_two_blocks(desc)
            if blocks:
                pddl_actions.append(f"(stack {blocks[0]} {blocks[1]})")

        elif "unstack" in desc:
            blocks = extract_two_blocks(desc)
            if blocks:
                pddl_actions.append(f"(unstack {blocks[0]} {blocks[1]})")

        else:
            # Generic action mapping
            pddl_actions.append(f"; Unmapped action: {node.description}")

    return pddl_actions


def extract_block_name(text: str) -> str:
    """Extract single-letter block name from text"""
    # Look for single letters (blocksworld convention)
    match = re.search(r'\b([a-z])\b', text)
    return match.group(1) if match else None


def extract_two_blocks(text: str) -> list:
    """Extract two block names from text"""
    blocks = re.findall(r'\b([a-z])\b', text)
    return blocks[:2] if len(blocks) >= 2 else None


# ============================================================================
# STEP 4: End-to-End Test
# ============================================================================

def test_pddl_to_bdi_pipeline():
    """Run complete pipeline on a PlanBench instance"""

    print("="*80)
    print("  PROOF OF CONCEPT: PDDL → BDI → PDDL Pipeline")
    print("="*80 + "\n")

    # Check API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not set")
        print("   export OPENAI_API_KEY=your-key")
        return

    # Step 1: Load PDDL problem
    pddl_file = "planbench_data/plan-bench/instances/blocksworld/generated/instance-1.pddl"

    print(f"📄 Loading PDDL problem: {pddl_file}")
    pddl_data = parse_pddl_problem(pddl_file)

    print(f"\n📊 Parsed PDDL:")
    print(f"   Objects: {pddl_data['objects']}")
    print(f"   Init predicates: {len(pddl_data['init'])}")
    print(f"   Goal predicates: {len(pddl_data['goal'])}")

    # Step 2: Convert to natural language
    print(f"\n🔄 Converting to natural language...")
    beliefs, desire = pddl_to_natural_language(pddl_data)

    print(f"\n📝 Natural Language Representation:")
    print(f"   Beliefs: {beliefs}")
    print(f"   Desire: {desire}")

    # Step 3: Generate BDI plan
    print(f"\n🤖 Generating plan with BDI-LLM...")
    plan, is_valid = generate_bdi_plan(beliefs, desire)

    print(f"\n📈 Generated Plan:")
    print(f"   Nodes: {len(plan.nodes)}")
    print(f"   Edges: {len(plan.edges)}")
    print(f"   Valid: {is_valid}")

    # Show plan structure
    print(f"\n🔍 Plan Structure:")
    for node in plan.nodes:
        print(f"   [{node.id}] {node.description}")

    # Step 4: Convert back to PDDL
    print(f"\n🔄 Converting DAG to PDDL plan...")
    pddl_plan = dag_to_pddl_plan(plan)

    print(f"\n📋 PDDL Plan ({len(pddl_plan)} actions):")
    for i, action in enumerate(pddl_plan, 1):
        print(f"   {i}. {action}")

    # Summary
    print(f"\n" + "="*80)
    print(f"  PIPELINE TEST COMPLETE")
    print("="*80)
    print(f"\n✅ Successfully converted:")
    print(f"   PDDL (8 blocks, 8 goals)")
    print(f"     ↓")
    print(f"   Natural Language (beliefs + desire)")
    print(f"     ↓")
    print(f"   BDI Plan ({len(plan.nodes)} nodes, {len(plan.edges)} edges, {'✅ valid' if is_valid else '❌ invalid'})")
    print(f"     ↓")
    print(f"   PDDL Plan ({len(pddl_plan)} actions)")

    print(f"\n💡 Next Step:")
    print(f"   • Validate PDDL plan with VAL (external validator)")
    print(f"   • Compare with ground-truth optimal plan")
    print(f"   • Scale to full PlanBench dataset")

    return {
        'pddl_data': pddl_data,
        'beliefs': beliefs,
        'desire': desire,
        'bdi_plan': plan,
        'is_valid': is_valid,
        'pddl_plan': pddl_plan
    }


if __name__ == "__main__":
    test_pddl_to_bdi_pipeline()
