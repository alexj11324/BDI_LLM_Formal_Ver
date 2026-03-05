#!/usr/bin/env python3
"""
Add Symbolic Verification to BDI-LLM
====================================

Integrates PDDL symbolic verification using VAL (PlanBench validator)

Two-layer verification approach:
1. Graph-theoretic verification (existing) - DAG structure
2. Symbolic verification (new) - PDDL semantics

Author: BDI-LLM Research
Date: 2026-02-03
"""

import subprocess
import tempfile
import os
from pathlib import Path
from typing import Tuple, List


# ============================================================================
# Symbolic Verifier using VAL
# ============================================================================

class PDDLSymbolicVerifier:
    """
    Symbolic verifier for PDDL plans using VAL tool

    Checks:
    - Preconditions satisfied at each step
    - Effects correctly applied
    - Goal state reachable
    - Physical constraints (domain-specific)
    """

    def __init__(self, val_path: str = "planbench_data/planner_tools/VAL/validate"):
        self.val_path = val_path

    def verify_pddl_plan(
        self,
        domain_file: str,
        problem_file: str,
        plan_actions: List[str]
    ) -> Tuple[bool, List[str]]:
        """
        Verify a PDDL plan using VAL

        Args:
            domain_file: Path to PDDL domain file
            problem_file: Path to PDDL problem file
            plan_actions: List of PDDL actions, e.g., ["(pick-up a)", "(stack a b)"]

        Returns:
            (is_valid, errors)
        """
        # Create temporary plan file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pddl', delete=False) as f:
            plan_file = f.name
            for action in plan_actions:
                f.write(f"{action}\n")

        try:
            # Run VAL validator
            result = subprocess.run(
                [self.val_path, domain_file, problem_file, plan_file],
                capture_output=True,
                text=True,
                timeout=30
            )

            # Parse output
            output = result.stdout + result.stderr

            # VAL returns specific strings for validation results
            if "Plan valid" in output or "Plan executed successfully" in output:
                return True, []
            elif "Plan failed" in output or "Bad plan" in output:
                # Extract error details
                errors = self._parse_val_errors(output)
                return False, errors
            else:
                # Unknown output
                return False, [f"VAL validator output unclear: {output[:200]}"]

        except subprocess.TimeoutExpired:
            return False, ["VAL validation timeout"]
        except Exception as e:
            return False, [f"VAL execution error: {str(e)}"]
        finally:
            # Clean up temp file
            sys.path.insert(0, str(Path(__file__).parents[1]))
            if os.path.exists(plan_file):
                os.unlink(plan_file)

    def _parse_val_errors(self, val_output: str) -> List[str]:
        """Extract error messages from VAL output"""
        errors = []

        # Common VAL error patterns
        if "Precondition not satisfied" in val_output:
            errors.append("Precondition violation detected")
        if "Goal not achieved" in val_output:
            errors.append("Plan does not achieve goal")
        if "Invalid action" in val_output:
            errors.append("Invalid action in plan")

        # If no specific errors, return full output snippet
        if not errors:
            errors.append(val_output[:500])

        return errors


# ============================================================================
# Domain-Specific Validators
# ============================================================================

class BlocksworldPhysicsValidator:
    """
    Validates blocksworld-specific physical constraints

    Rules:
    - Can only pick up clear blocks (nothing on top)
    - Can only stack on clear blocks
    - Hand can hold at most one block
    - Cannot pick up block while holding another
    """

    @staticmethod
    def validate_blocksworld_plan(plan_actions: List[str], init_state: dict) -> Tuple[bool, List[str]]:
        """
        Simulate plan execution and check physical constraints

        Args:
            plan_actions: List of PDDL actions
            init_state: Initial state from PDDL problem
                {
                    'on_table': ['a', 'b', 'c'],
                    'on': [('a', 'b')],  # a is on b
                    'clear': ['a', 'c'],
                    'holding': None
                }
        """
        errors = []

        # Simulate state
        state = {
            'on_table': set(init_state.get('on_table', [])),
            'on': set(init_state.get('on', [])),
            'clear': set(init_state.get('clear', [])),
            'holding': init_state.get('holding', None)
        }

        for i, action in enumerate(plan_actions):
            action_lower = action.lower()

            # Parse action
            if 'pick-up' in action_lower:
                block = BlocksworldPhysicsValidator._extract_block(action)

                # Check preconditions
                if block not in state['clear']:
                    errors.append(f"Step {i+1}: Cannot pick-up {block} - not clear")
                if state['holding'] is not None:
                    errors.append(f"Step {i+1}: Cannot pick-up {block} - hand not empty")
                if block not in state['on_table']:
                    errors.append(f"Step {i+1}: Cannot pick-up {block} - not on table")

                # Apply effects
                if block in state['on_table']:
                    state['on_table'].remove(block)
                if block in state['clear']:
                    state['clear'].remove(block)
                state['holding'] = block

            elif 'put-down' in action_lower:
                block = BlocksworldPhysicsValidator._extract_block(action)

                if state['holding'] != block:
                    errors.append(f"Step {i+1}: Cannot put-down {block} - not holding it")

                state['on_table'].add(block)
                state['clear'].add(block)
                state['holding'] = None

            elif 'stack' in action_lower:
                blocks = BlocksworldPhysicsValidator._extract_two_blocks(action)
                if len(blocks) >= 2:
                    block_from, block_to = blocks[0], blocks[1]

                    if state['holding'] != block_from:
                        errors.append(f"Step {i+1}: Cannot stack {block_from} - not holding it")
                    if block_to not in state['clear']:
                        errors.append(f"Step {i+1}: Cannot stack on {block_to} - not clear")

                    state['on'].add((block_from, block_to))
                    state['clear'].add(block_from)
                    if block_to in state['clear']:
                        state['clear'].remove(block_to)
                    state['holding'] = None

            elif 'unstack' in action_lower:
                blocks = BlocksworldPhysicsValidator._extract_two_blocks(action)
                if len(blocks) >= 2:
                    block_from, block_to = blocks[0], blocks[1]

                    if block_from not in state['clear']:
                        errors.append(f"Step {i+1}: Cannot unstack {block_from} - not clear")
                    if state['holding'] is not None:
                        errors.append(f"Step {i+1}: Cannot unstack - hand not empty")

                    if (block_from, block_to) in state['on']:
                        state['on'].remove((block_from, block_to))
                    state['clear'].add(block_to)
                    if block_from in state['clear']:
                        state['clear'].remove(block_from)
                    state['holding'] = block_from

        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def _extract_block(action: str) -> str:
        """Extract single block name from action"""
        import re
        match = re.search(r'\b([a-z])\b', action.lower())
        return match.group(1) if match else None

    @staticmethod
    def _extract_two_blocks(action: str) -> List[str]:
        """Extract two block names from action"""
        import re
        blocks = re.findall(r'\b([a-z])\b', action.lower())
        return blocks[:2] if len(blocks) >= 2 else []


# ============================================================================
# Integrated Verification Pipeline
# ============================================================================

class IntegratedVerifier:
    """
    Two-layer verification:
    1. Graph-theoretic (DAG structure)
    2. Symbolic (PDDL semantics)
    """

    def __init__(self, domain: str = "blocksworld"):
        self.domain = domain
        self.pddl_verifier = PDDLSymbolicVerifier()
        self.physics_validator = BlocksworldPhysicsValidator() if domain == "blocksworld" else None

    def verify_plan(
        self,
        bdi_plan,  # BDIPlan object
        pddl_actions: List[str],
        domain_file: str,
        problem_file: str,
        init_state: dict = None
    ) -> dict:
        """
        Run full verification pipeline

        Returns:
            {
                'graph_valid': bool,
                'graph_errors': [...],
                'symbolic_valid': bool,
                'symbolic_errors': [...],
                'physics_valid': bool,
                'physics_errors': [...],
                'overall_valid': bool
            }
        """
        from src.bdi_llm.verifier import PlanVerifier

        results = {}

        # Layer 1: Graph verification
        G = bdi_plan.to_networkx()
        graph_valid, graph_errors = PlanVerifier.verify(G)
        results['graph_valid'] = graph_valid
        results['graph_errors'] = graph_errors

        # Layer 2: PDDL symbolic verification (if graph valid)
        if graph_valid and domain_file and problem_file:
            symbolic_valid, symbolic_errors = self.pddl_verifier.verify_pddl_plan(
                domain_file, problem_file, pddl_actions
            )
            results['symbolic_valid'] = symbolic_valid
            results['symbolic_errors'] = symbolic_errors
        else:
            results['symbolic_valid'] = False
            results['symbolic_errors'] = ["Skipped (graph invalid or files missing)"]

        # Layer 3: Domain-specific physics (if blocksworld)
        if self.physics_validator and init_state:
            physics_valid, physics_errors = self.physics_validator.validate_blocksworld_plan(
                pddl_actions, init_state
            )
            results['physics_valid'] = physics_valid
            results['physics_errors'] = physics_errors
        else:
            results['physics_valid'] = True  # No domain validator
            results['physics_errors'] = []

        # Overall verdict
        results['overall_valid'] = (
            results['graph_valid'] and
            results['symbolic_valid'] and
            results['physics_valid']
        )

        return results


# ============================================================================
# Demo
# ============================================================================

def demo_symbolic_verification():
    """Demonstrate symbolic verification on a simple blocksworld problem"""

    print("="*80)
    print("  SYMBOLIC VERIFICATION DEMO")
    print("="*80 + "\n")

    # Example: Simple blocksworld problem
    print("Scenario: Stack block A on block B")
    print("\nInitial state:")
    print("  - Block A on table (clear)")
    print("  - Block B on table (clear)")
    print("  - Hand empty\n")

    init_state = {
        'on_table': ['a', 'b'],
        'on': [],
        'clear': ['a', 'b'],
        'holding': None
    }

    # Test Case 1: Valid plan
    print("Test Case 1: Valid Plan")
    valid_plan = [
        "(pick-up a)",
        "(stack a b)"
    ]
    print(f"Actions: {valid_plan}")

    validator = BlocksworldPhysicsValidator()
    is_valid, errors = validator.validate_blocksworld_plan(valid_plan, init_state)

    if is_valid:
        print("✅ VALID - Physics constraints satisfied\n")
    else:
        print(f"❌ INVALID - Errors: {errors}\n")

    # Test Case 2: Invalid plan (pick up block that's not clear)
    print("Test Case 2: Invalid Plan (violates clear constraint)")
    init_state_invalid = {
        'on_table': ['b'],
        'on': [('a', 'b')],  # a is on b
        'clear': ['a'],       # only a is clear
        'holding': None
    }

    invalid_plan = [
        "(pick-up b)",  # ERROR: b is not clear (a is on top)
        "(stack b c)"
    ]
    print(f"Actions: {invalid_plan}")
    print("Initial: A is on B (so B is NOT clear)")

    is_valid, errors = validator.validate_blocksworld_plan(invalid_plan, init_state_invalid)

    if is_valid:
        print("✅ VALID\n")
    else:
        print(f"❌ INVALID - Errors detected:")
        for err in errors:
            print(f"   • {err}")
        print()

    print("="*80)
    print("  Symbolic verification catches errors that graph verification misses!")
    print("="*80)


if __name__ == "__main__":
    demo_symbolic_verification()
