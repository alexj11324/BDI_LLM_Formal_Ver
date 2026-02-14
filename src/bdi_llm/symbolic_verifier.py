#!/usr/bin/env python3
"""
Symbolic Verifier - Layer 2 of Verification Architecture
========================================================

Implements PDDL symbolic verification using VAL tool.

This addresses the gap identified by advisor's methodology:
"验证器会像编译器进行语法检查和类型检查一样，对这个形式化计划进行逻辑上的检查。"

Author: BDI-LLM Research
Date: 2026-02-03
"""

import subprocess
import tempfile
import os
import re
from pathlib import Path
from typing import Tuple, List, Dict


class PDDLSymbolicVerifier:
    """
    Symbolic verifier using VAL (Validating Action Language)

    VAL checks:
    - Preconditions satisfied at each step
    - Effects correctly applied
    - Goal state reachable
    - Action parameters valid
    - Type constraints met
    """

    def __init__(self, val_path: str = None):
        """
        Args:
            val_path: Path to VAL validator executable
                     Default: planbench_data/planner_tools/VAL/validate
        """
        if val_path is None:
            # Auto-detect VAL in PlanBench
            base = Path(__file__).parent.parent.parent
            val_path = base / "planbench_data/planner_tools/VAL/validate"

        self.val_path = str(val_path)

        # Verify VAL exists
        if not os.path.exists(self.val_path):
            raise FileNotFoundError(
                f"VAL validator not found at: {self.val_path}\n"
                f"Please ensure PlanBench is properly installed."
            )

    def verify_plan(
        self,
        domain_file: str,
        problem_file: str,
        plan_actions: List[str],
        verbose: bool = False
    ) -> Tuple[bool, List[str]]:
        """
        Verify PDDL plan using VAL

        Args:
            domain_file: Path to PDDL domain file
            problem_file: Path to PDDL problem file
            plan_actions: List of PDDL actions, e.g., ["(pick-up a)", "(stack a b)"]
            verbose: If True, include full VAL output in errors

        Returns:
            (is_valid, error_messages)

        Example:
            >>> verifier = PDDLSymbolicVerifier()
            >>> is_valid, errors = verifier.verify_plan(
            ...     "domain.pddl",
            ...     "problem.pddl",
            ...     ["(pick-up a)", "(stack a b)"]
            ... )
            >>> print(f"Valid: {is_valid}, Errors: {errors}")
        """
        if not plan_actions:
            return False, ["Empty plan - no actions to verify"]

        # Create temporary plan file
        plan_file = self._create_plan_file(plan_actions)

        try:
            # Run VAL validator with -v for verbose output
            # -v provides: specific failed action, unsatisfied preconditions,
            # and Plan Repair Advice with concrete predicates to fix
            result = subprocess.run(
                [self.val_path, '-v', domain_file, problem_file, plan_file],
                capture_output=True,
                text=True,
                timeout=30
            )

            output = result.stdout + result.stderr

            # Parse VAL output
            is_valid, errors = self._parse_val_output(output, verbose)

            return is_valid, errors

        except subprocess.TimeoutExpired:
            return False, ["VAL validation timeout (>30s)"]

        except FileNotFoundError:
            return False, [f"VAL executable not found: {self.val_path}"]

        except OSError as e:
            # Handle "Exec format error" (e.g. Linux binary on Mac)
            if e.errno == 8:
                return False, [f"VAL executable incompatible with current OS (Exec format error): {self.val_path}"]
            return False, [f"VAL execution error (OSError): {str(e)}"]

        except Exception as e:
            return False, [f"VAL execution error: {str(e)}"]

        finally:
            # Clean up temp file
            if os.path.exists(plan_file):
                os.unlink(plan_file)

    def _create_plan_file(self, actions: List[str]) -> str:
        """Create temporary PDDL plan file"""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.pddl',
            delete=False,
            prefix='bdi_plan_'
        ) as f:
            # Write plan actions
            for action in actions:
                # Ensure action is properly formatted
                action_str = action.strip()
                if not action_str.startswith('('):
                    action_str = f"({action_str})"
                f.write(f"{action_str}\n")

            return f.name

    def _parse_val_output(self, output: str, verbose: bool) -> Tuple[bool, List[str]]:
        """
        Parse VAL validator output (with -v verbose flag)

        VAL -v outputs patterns like:
        - "Plan executed successfully - checking goal" + no "Goal not satisfied" → Valid
        - "Plan failed because of unsatisfied precondition in:" → Precondition failure
        - "Goal not satisfied" / "Plan invalid" → Goal not achieved
        - "Error in type-checking!" → Type error in action parameters
        - "Bad plan" / "Bad problem file!" → Structural PDDL error
        """
        errors = []

        # Check for full success: plan executed AND goal satisfied
        if "Plan executed successfully" in output and "Goal not satisfied" not in output and "Plan invalid" not in output:
            return True, []

        # Check for goal not satisfied (plan executes but doesn't reach goal)
        if "Goal not satisfied" in output or "Plan invalid" in output:
            errors = self._extract_val_errors(output)
            if verbose:
                errors.append(f"\nFull VAL output:\n{output}")
            return False, errors

        # Check for precondition / execution failure
        if "Plan failed" in output or "Bad plan" in output:
            errors = self._extract_val_errors(output)
            if verbose:
                errors.append(f"\nFull VAL output:\n{output}")
            return False, errors

        # Check for type-checking errors
        if "Error in type-checking" in output or "Bad problem file" in output:
            errors = self._extract_val_errors(output)
            if verbose:
                errors.append(f"\nFull VAL output:\n{output}")
            return False, errors

        # Unknown output format
        if verbose:
            errors.append(f"VAL output unclear:\n{output}")
        else:
            errors.append("VAL validation result unclear (enable verbose for details)")

        return False, errors

    def _extract_val_errors(self, output: str) -> List[str]:
        """Extract specific error messages from VAL -v verbose output.

        With -v flag, VAL provides:
        - Which action failed and at which step
        - Unsatisfied preconditions with specific predicates
        - Plan Repair Advice with concrete fixes
        """
        errors = []

        # Pattern 1 (verbose): Unsatisfied precondition with specific action
        # "Plan failed because of unsatisfied precondition in:\n(action-name args)"
        precond_verbose = re.search(
            r"Plan failed because of unsatisfied precondition in:\s*\n\s*(\(.+?\))",
            output, re.DOTALL
        )
        if precond_verbose:
            failed_action = precond_verbose.group(1).strip()
            errors.append(f"Unsatisfied precondition in action: {failed_action}")

        # Pattern 2 (verbose): Plan Repair Advice section
        # Captures the entire repair advice block
        repair_advice = re.search(
            r"Plan Repair Advice:\s*\n(.*?)(?:\n\s*\n|\nFailed plans:|\Z)",
            output, re.DOTALL
        )
        if repair_advice:
            advice_text = repair_advice.group(1).strip()
            errors.append(f"VAL Repair Advice: {advice_text}")

        # Pattern 3: Goal not satisfied
        if "Goal not satisfied" in output:
            errors.append("Plan executed but goal not satisfied")

        # Pattern 4 (legacy): Precondition not satisfied (non-verbose format)
        precond_pattern = r"Precondition not satisfied: (.+)"
        for match in re.finditer(precond_pattern, output):
            errors.append(f"Precondition violation: {match.group(1)}")

        # Pattern 5: Type-checking errors
        if "Error in type-checking" in output:
            errors.append("Type-checking error: action parameters have invalid types")

        # Pattern 6: Invalid action parameters
        invalid_action_pattern = r"Invalid action: (.+)"
        for match in re.finditer(invalid_action_pattern, output):
            errors.append(f"Invalid action: {match.group(1)}")

        # Pattern 7: Type errors
        type_error_pattern = r"Type error: (.+)"
        for match in re.finditer(type_error_pattern, output):
            errors.append(f"Type error: {match.group(1)}")

        # If no specific errors extracted, provide generic message
        if not errors:
            lines = output.split('\n')
            for line in lines:
                if 'error' in line.lower() or 'fail' in line.lower():
                    errors.append(line.strip())
                    break

            if not errors:
                errors.append("Plan validation failed (reason unclear)")

        return errors


class BlocksworldPhysicsValidator:
    """
    Domain-specific validator for Blocksworld

    Validates physical constraints that VAL may not catch:
    - Can only pick up clear blocks
    - Hand holds at most one block
    - Cannot stack on non-clear blocks
    """

    @staticmethod
    def validate_plan(
        plan_actions: List[str],
        init_state: Dict
    ) -> Tuple[bool, List[str]]:
        """
        Simulate plan execution and check physical constraints

        Args:
            plan_actions: List of PDDL actions
            init_state: Initial state dictionary:
                {
                    'on_table': ['a', 'b'],
                    'on': [('a', 'b')],  # a is on b
                    'clear': ['a', 'c'],
                    'holding': None
                }

        Returns:
            (is_valid, error_messages)
        """
        errors = []

        # Initialize state
        state = {
            'on_table': set(init_state.get('on_table', [])),
            'on': set(init_state.get('on', [])),
            'clear': set(init_state.get('clear', [])),
            'holding': init_state.get('holding', None)
        }

        # Simulate each action
        for i, action in enumerate(plan_actions):
            action_lower = action.lower()
            step_num = i + 1

            if 'pick-up' in action_lower or 'pickup' in action_lower:
                block = BlocksworldPhysicsValidator._extract_block(action)
                if not block:
                    errors.append(f"Step {step_num}: Cannot parse block from {action}")
                    continue

                # Check preconditions
                if block not in state['clear']:
                    errors.append(
                        f"Step {step_num}: Cannot pick-up {block} - block not clear "
                        f"(something on top)"
                    )

                if state['holding'] is not None:
                    errors.append(
                        f"Step {step_num}: Cannot pick-up {block} - hand already holding "
                        f"{state['holding']}"
                    )

                if block not in state['on_table']:
                    errors.append(
                        f"Step {step_num}: Cannot pick-up {block} - not on table"
                    )

                # Apply effects (if no errors so far)
                if block in state['on_table']:
                    state['on_table'].remove(block)
                if block in state['clear']:
                    state['clear'].remove(block)
                state['holding'] = block

            elif 'put-down' in action_lower or 'putdown' in action_lower:
                block = BlocksworldPhysicsValidator._extract_block(action)
                if not block:
                    errors.append(f"Step {step_num}: Cannot parse block from {action}")
                    continue

                if state['holding'] != block:
                    errors.append(
                        f"Step {step_num}: Cannot put-down {block} - not holding it "
                        f"(holding {state['holding']})"
                    )

                state['on_table'].add(block)
                state['clear'].add(block)
                state['holding'] = None

            elif 'stack' in action_lower:
                blocks = BlocksworldPhysicsValidator._extract_two_blocks(action)
                if len(blocks) < 2:
                    errors.append(
                        f"Step {step_num}: Cannot parse blocks from stack action: {action}"
                    )
                    continue

                block_from, block_to = blocks[0], blocks[1]

                if state['holding'] != block_from:
                    errors.append(
                        f"Step {step_num}: Cannot stack {block_from} - not holding it "
                        f"(holding {state['holding']})"
                    )

                if block_to not in state['clear']:
                    errors.append(
                        f"Step {step_num}: Cannot stack on {block_to} - not clear"
                    )

                state['on'].add((block_from, block_to))
                state['clear'].add(block_from)
                if block_to in state['clear']:
                    state['clear'].remove(block_to)
                state['holding'] = None

            elif 'unstack' in action_lower:
                blocks = BlocksworldPhysicsValidator._extract_two_blocks(action)
                if len(blocks) < 2:
                    errors.append(
                        f"Step {step_num}: Cannot parse blocks from unstack action: {action}"
                    )
                    continue

                block_from, block_to = blocks[0], blocks[1]

                if block_from not in state['clear']:
                    errors.append(
                        f"Step {step_num}: Cannot unstack {block_from} - not clear"
                    )

                if state['holding'] is not None:
                    errors.append(
                        f"Step {step_num}: Cannot unstack - hand not empty "
                        f"(holding {state['holding']})"
                    )

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
        """
        Extract single block name from action.
        Handles both single-letter blocks (e.g. 'a') and multi-char blocks (e.g. 'block1').
        """
        # Clean action string: remove parens
        clean_action = action.lower().replace('(', ' ').replace(')', ' ')
        parts = clean_action.split()

        # parts[0] should be the action name (pick-up, put-down), parts[1] the argument
        if len(parts) > 1:
            return parts[1]

        # Fallback to regex if simple split fails (though split is safer for multi-char)
        match = re.search(r'\b([a-z0-9_-]+)\b', action.lower())
        return match.group(1) if match else None

    @staticmethod
    def _extract_two_blocks(action: str) -> List[str]:
        """
        Extract two block names from action.
        Handles both single-letter blocks and multi-char blocks.
        """
        # Clean action string: remove parens
        clean_action = action.lower().replace('(', ' ').replace(')', ' ')
        parts = clean_action.split()

        # parts[0] action name, parts[1] arg1, parts[2] arg2
        if len(parts) > 2:
            return parts[1:3]

        # Fallback to regex
        blocks = re.findall(r'\b([a-z0-9_-]+)\b', action.lower())
        # Filter out action keywords if caught by regex
        keywords = {'stack', 'unstack', 'pick-up', 'pickup', 'put-down', 'putdown'}
        filtered_blocks = [b for b in blocks if b not in keywords]

        return filtered_blocks[:2] if len(filtered_blocks) >= 2 else []


# ============================================================================
# Integrated Multi-Layer Verifier
# ============================================================================

class IntegratedVerifier:
    """
    Three-layer verification architecture:
    1. Structural (Graph/DAG)
    2. Symbolic (PDDL/VAL)
    3. Domain-specific (Physics)

    This implements the advisor's "compilation-verification" methodology.
    """

    def __init__(self, domain: str = "blocksworld", val_path: str = None):
        """
        Args:
            domain: Planning domain (e.g., "blocksworld", "logistics")
            val_path: Path to VAL validator (auto-detected if None)
        """
        self.domain = domain
        self.symbolic_verifier = PDDLSymbolicVerifier(val_path)

        # Domain-specific validators
        if domain == "blocksworld":
            self.physics_validator = BlocksworldPhysicsValidator()
        else:
            self.physics_validator = None

    def verify_full(
        self,
        bdi_plan,
        pddl_actions: List[str],
        domain_file: str = None,
        problem_file: str = None,
        init_state: Dict = None
    ) -> Dict:
        """
        Run complete three-layer verification

        Args:
            bdi_plan: BDIPlan object (for graph verification)
            pddl_actions: List of PDDL action strings
            domain_file: Path to PDDL domain file
            problem_file: Path to PDDL problem file
            init_state: Initial state dict (for physics validation)

        Returns:
            {
                'layers': {
                    'structural': {'valid': bool, 'errors': [...]},
                    'symbolic': {'valid': bool, 'errors': [...]},
                    'physics': {'valid': bool, 'errors': [...]}
                },
                'overall_valid': bool,
                'error_summary': str
            }
        """
        from src.bdi_llm.verifier import PlanVerifier

        results = {
            'layers': {},
            'overall_valid': False,
            'error_summary': ''
        }

        # Layer 1: Structural verification (Graph)
        G = bdi_plan.to_networkx()
        struct_valid, struct_errors = PlanVerifier.verify(G)
        results['layers']['structural'] = {
            'valid': struct_valid,
            'errors': struct_errors
        }

        # Layer 2: Symbolic verification (PDDL/VAL)
        if domain_file and problem_file and struct_valid:
            symb_valid, symb_errors = self.symbolic_verifier.verify_plan(
                domain_file, problem_file, pddl_actions
            )
            results['layers']['symbolic'] = {
                'valid': symb_valid,
                'errors': symb_errors
            }
        else:
            results['layers']['symbolic'] = {
                'valid': False,
                'errors': ["Skipped (missing files or structural errors)"]
            }

        # Layer 3: Physics validation (Domain-specific)
        if self.physics_validator and init_state:
            phys_valid, phys_errors = self.physics_validator.validate_plan(
                pddl_actions, init_state
            )
            results['layers']['physics'] = {
                'valid': phys_valid,
                'errors': phys_errors
            }
        else:
            results['layers']['physics'] = {
                'valid': True,  # No validator = assume valid
                'errors': []
            }

        # Overall verdict
        results['overall_valid'] = all(
            layer['valid'] for layer in results['layers'].values()
        )

        # Error summary
        if not results['overall_valid']:
            failed_layers = [
                name for name, layer in results['layers'].items()
                if not layer['valid']
            ]
            results['error_summary'] = f"Failed layers: {', '.join(failed_layers)}"
        else:
            results['error_summary'] = "All layers passed"

        return results
