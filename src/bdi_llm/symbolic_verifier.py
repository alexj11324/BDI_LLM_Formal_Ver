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

import os
import re
from typing import Any

from .config import Config
from .val_runner import run_val


class PDDLSymbolicVerifier:
    """
    Symbolic verifier using VAL (Validating Action Language)

    VAL checks:
    - Preconditions satisfied at each step
    - Effects correctly applied
    - Goal state reachable
    - Action parameters valid
    - Type constraints met

    Low-level VAL subprocess management is delegated to :mod:`val_runner`.
    """

    def __init__(self, val_path: str = None):
        """
        Args:
            val_path: Path to VAL validator executable
                     Default: workspaces/planbench_data/planner_tools/VAL/validate
        """
        if val_path is None:
            val_path = Config.VAL_VALIDATOR_PATH

        self.val_path = str(val_path)

        # Verify VAL exists
        if not os.path.exists(self.val_path):
            raise FileNotFoundError(
                f"VAL validator not found at: {self.val_path}\nPlease ensure PlanBench is properly installed."
            )

    def verify_plan(
        self,
        domain_file: str,
        problem_file: str,
        plan_actions: list[str],
        verbose: bool = False,
        check_goal: bool = True,
    ) -> tuple[bool, list[str]]:
        """
        Verify PDDL plan using VAL

        Args:
            domain_file: Path to PDDL domain file
            problem_file: Path to PDDL problem file
            plan_actions: List of PDDL actions, e.g., ["(pick-up a)", "(stack a b)"]
            verbose: If True, include full VAL output in errors
            check_goal: If False (prefix verification), treat
                "executed but goal not satisfied" as success.

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
        return run_val(
            self.val_path,
            domain_file,
            problem_file,
            plan_actions,
            check_goal=check_goal,
            verbose=verbose,
        )


PHYSICS_VALIDATORS = {}


def register_physics_validator(domain_name: str, validator_cls):
    """Register a domain-specific physics validator."""
    PHYSICS_VALIDATORS[domain_name] = validator_cls


def get_physics_validator(domain_name: str):
    """Get a domain-specific physics validator instance."""
    cls = PHYSICS_VALIDATORS.get(domain_name)
    return cls() if cls is not None else None


class BlocksworldPhysicsValidator:
    """
    Domain-specific validator for Blocksworld

    Validates physical constraints that VAL may not catch:
    - Can only pick up clear blocks
    - Hand holds at most one block
    - Cannot stack on non-clear blocks
    """

    # Compiled regex pattern for block extraction
    _re_block = re.compile(r"\b([a-z0-9_-]+)\b")

    @staticmethod
    def _initial_state(init_state: dict) -> dict[str, Any]:
        """Build mutable simulation state from raw init_state."""
        return {
            "on_table": set(init_state.get("on_table", [])),
            "on": set(init_state.get("on", [])),
            "clear": set(init_state.get("clear", [])),
            "holding": init_state.get("holding", None),
        }

    @staticmethod
    def _handle_pickup(
        action: str,
        state: dict[str, Any],
        step_num: int,
        errors: list[str],
    ) -> None:
        block = BlocksworldPhysicsValidator._extract_block(action)
        if not block:
            errors.append(f"Step {step_num}: Cannot parse block from {action}")
            return

        if block not in state["clear"]:
            errors.append(f"Step {step_num}: Cannot pick-up {block} - block not clear (something on top)")
        if state["holding"] is not None:
            errors.append(f"Step {step_num}: Cannot pick-up {block} - hand already holding {state['holding']}")
        if block not in state["on_table"]:
            errors.append(f"Step {step_num}: Cannot pick-up {block} - not on table")

        if block in state["on_table"]:
            state["on_table"].remove(block)
        if block in state["clear"]:
            state["clear"].remove(block)
        state["holding"] = block

    @staticmethod
    def _handle_putdown(
        action: str,
        state: dict[str, Any],
        step_num: int,
        errors: list[str],
    ) -> None:
        block = BlocksworldPhysicsValidator._extract_block(action)
        if not block:
            errors.append(f"Step {step_num}: Cannot parse block from {action}")
            return

        if state["holding"] != block:
            errors.append(f"Step {step_num}: Cannot put-down {block} - not holding it (holding {state['holding']})")

        state["on_table"].add(block)
        state["clear"].add(block)
        state["holding"] = None

    @staticmethod
    def _handle_unstack(
        action: str,
        state: dict[str, Any],
        step_num: int,
        errors: list[str],
    ) -> None:
        blocks = BlocksworldPhysicsValidator._extract_two_blocks(action)
        if len(blocks) < 2:
            errors.append(f"Step {step_num}: Cannot parse blocks from unstack action: {action}")
            return

        block_from, block_to = blocks[0], blocks[1]
        if block_from not in state["clear"]:
            errors.append(f"Step {step_num}: Cannot unstack {block_from} - not clear")
        if state["holding"] is not None:
            errors.append(f"Step {step_num}: Cannot unstack - hand not empty (holding {state['holding']})")

        if (block_from, block_to) in state["on"]:
            state["on"].remove((block_from, block_to))
        state["clear"].add(block_to)
        if block_from in state["clear"]:
            state["clear"].remove(block_from)
        state["holding"] = block_from

    @staticmethod
    def _handle_stack(action: str, state: dict[str, Any], step_num: int, errors: list[str]) -> None:
        blocks = BlocksworldPhysicsValidator._extract_two_blocks(action)
        if len(blocks) < 2:
            errors.append(f"Step {step_num}: Cannot parse blocks from stack action: {action}")
            return

        block_from, block_to = blocks[0], blocks[1]
        if state["holding"] != block_from:
            errors.append(f"Step {step_num}: Cannot stack {block_from} - not holding it (holding {state['holding']})")
        if block_to not in state["clear"]:
            errors.append(f"Step {step_num}: Cannot stack on {block_to} - not clear")

        state["on"].add((block_from, block_to))
        state["clear"].add(block_from)
        if block_to in state["clear"]:
            state["clear"].remove(block_to)
        state["holding"] = None

    @staticmethod
    def validate_plan(plan_actions: list[str], init_state: dict) -> tuple[bool, list[str]]:
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
        errors: list[str] = []
        state = BlocksworldPhysicsValidator._initial_state(init_state)

        handlers = (
            (("pick-up", "pickup"), BlocksworldPhysicsValidator._handle_pickup),
            (("put-down", "putdown"), BlocksworldPhysicsValidator._handle_putdown),
            (("unstack",), BlocksworldPhysicsValidator._handle_unstack),
            (("stack",), BlocksworldPhysicsValidator._handle_stack),
        )

        for i, action in enumerate(plan_actions):
            action_lower = action.lower()
            step_num = i + 1
            for keywords, handler in handlers:
                if any(keyword in action_lower for keyword in keywords):
                    handler(action, state, step_num, errors)
                    break

        is_valid = len(errors) == 0
        return is_valid, errors

    @staticmethod
    def _extract_block(action: str) -> str:
        """
        Extract single block name from action.
        Handles both single-letter blocks (e.g. 'a') and multi-char blocks (e.g. 'block1').
        """
        # Clean action string: remove parens
        clean_action = action.lower().replace("(", " ").replace(")", " ")
        parts = clean_action.split()

        # parts[0] should be the action name (pick-up, put-down), parts[1] the argument
        if len(parts) > 1:
            return parts[1]

        # Fallback to regex if simple split fails
        matches = BlocksworldPhysicsValidator._re_block.findall(action.lower())
        keywords = {"stack", "unstack", "pick-up", "pickup", "put-down", "putdown"}
        for match in matches:
            if match not in keywords:
                return match
        return None

    @staticmethod
    def _extract_two_blocks(action: str) -> list[str]:
        """
        Extract two block names from action.
        Handles both single-letter blocks and multi-char blocks.
        """
        # Clean action string: remove parens
        clean_action = action.lower().replace("(", " ").replace(")", " ")
        parts = clean_action.split()

        # parts[0] action name, parts[1] arg1, parts[2] arg2
        if len(parts) > 2:
            return parts[1:3]

        # Fallback to regex
        blocks = BlocksworldPhysicsValidator._re_block.findall(action.lower())
        # Filter out action keywords if caught by regex
        keywords = {"stack", "unstack", "pick-up", "pickup", "put-down", "putdown"}
        filtered_blocks = [b for b in blocks if b not in keywords]

        return filtered_blocks[:2] if len(filtered_blocks) >= 2 else []


# Register domain-specific validators
register_physics_validator("blocksworld", BlocksworldPhysicsValidator)


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

        # Domain-specific validators (loaded via robust registry)
        self.physics_validator = get_physics_validator(domain)

    @staticmethod
    def _truncate_errors(errors: list[str], limit: int) -> list[str]:
        """Return a compact, de-blanked error list."""
        if not errors:
            return []
        compact = [str(err).strip() for err in errors if str(err).strip()]
        return compact[:limit]

    @staticmethod
    def build_planner_feedback(
        verification_result: dict[str, Any],
        max_errors_per_layer: int = 3,
    ) -> dict[str, Any]:
        """
        Convert verifier output into planner-oriented repair feedback.

        This keeps verifier internals encapsulated while exposing concise,
        cross-layer diagnostics for repair prompting.
        """
        layers = verification_result.get("layers", {}) or {}
        failed_layers: list[str] = []
        layer_status: dict[str, str] = {}
        key_errors: dict[str, list[str]] = {}

        for layer_name in ("structural", "symbolic", "physics"):
            layer = layers.get(layer_name)
            if layer is None:
                layer_status[layer_name] = "unknown"
                key_errors[layer_name] = []
                continue

            is_valid = bool(layer.get("valid", False))
            layer_status[layer_name] = "pass" if is_valid else "fail"
            key_errors[layer_name] = IntegratedVerifier._truncate_errors(
                layer.get("errors", []),
                max_errors_per_layer,
            )
            if not is_valid:
                failed_layers.append(layer_name)

        symbolic_errors = key_errors.get("symbolic", [])
        val_repair_advice: list[str] = []
        for err in symbolic_errors:
            if err.startswith("VAL Repair Advice:"):
                advice = err.split("VAL Repair Advice:", 1)[1].strip()
                if advice:
                    val_repair_advice.append(advice)

        repair_focus: list[str] = []
        if "structural" in failed_layers:
            repair_focus.append("Fix graph structure first: produce one weakly connected DAG with no cycles.")
        if "symbolic" in failed_layers:
            if val_repair_advice:
                repair_focus.append("Prioritize VAL repair advice and add prerequisite actions before failing steps.")
            else:
                repair_focus.append("Fix symbolic precondition/goal failures before optimizing the plan.")
        if "physics" in failed_layers:
            repair_focus.append("Respect domain physics constraints when ordering and parameterizing actions.")
        if not repair_focus and verification_result.get("overall_valid", False):
            repair_focus.append("No verifier failures detected.")

        error_summary = verification_result.get("error_summary")
        if not error_summary:
            if failed_layers:
                error_summary = f"Failed layers: {', '.join(failed_layers)}"
            else:
                error_summary = "All layers passed"

        return {
            "error_summary": error_summary,
            "overall_valid": bool(verification_result.get("overall_valid", False)),
            "failed_layers": failed_layers,
            "layer_status": layer_status,
            "key_errors": key_errors,
            "val_repair_advice": val_repair_advice,
            "repair_focus": repair_focus,
        }

    def verify_full(
        self,
        bdi_plan,
        pddl_actions: list[str],
        domain_file: str = None,
        problem_file: str = None,
        init_state: dict = None,
    ) -> dict:
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
                    'structural': {
                        'valid': bool,
                        'hard_errors': [...],
                        'warnings': [...]
                    },
                    'symbolic': {'valid': bool, 'errors': [...]},
                    'physics': {'valid': bool, 'errors': [...]}
                },
                'overall_valid': bool,
                'error_summary': str,
                'planner_feedback': {
                    'failed_layers': [...],
                    'layer_status': {...},
                    'key_errors': {...},
                    'val_repair_advice': [...],
                    'repair_focus': [...]
                }
            }
        """
        from src.bdi_llm.verifier import PlanVerifier

        results = {
            "layers": {},
            "overall_valid": False,
            "error_summary": "",
            "planner_feedback": {},
        }

        # Layer 1: Structural verification (Graph)
        G = bdi_plan.to_networkx()
        struct_result = PlanVerifier.verify(G)
        results["layers"]["structural"] = {
            "valid": struct_result.is_valid,
            "hard_errors": struct_result.hard_errors,
            "warnings": struct_result.warnings,
        }

        # Layer 2: Symbolic verification (PDDL/VAL)
        # Proceed if no hard structural errors (warnings are OK)
        if domain_file and problem_file and not struct_result.should_block_execution:
            symb_valid, symb_errors = self.symbolic_verifier.verify_plan(domain_file, problem_file, pddl_actions)
            results["layers"]["symbolic"] = {"valid": symb_valid, "errors": symb_errors}
        else:
            reason = "missing PDDL files" if not (domain_file and problem_file) else "structural hard errors"
            results["layers"]["symbolic"] = {"valid": False, "errors": [f"Skipped ({reason})"]}

        # Layer 3: Physics validation (Domain-specific)
        if self.physics_validator and init_state:
            phys_valid, phys_errors = self.physics_validator.validate_plan(pddl_actions, init_state)
            results["layers"]["physics"] = {"valid": phys_valid, "errors": phys_errors}
        else:
            results["layers"]["physics"] = {
                "valid": True,  # No validator = assume valid
                "errors": [],
            }

        # Overall verdict
        results["overall_valid"] = all(layer["valid"] for layer in results["layers"].values())

        # Error summary
        if not results["overall_valid"]:
            failed_layers = [name for name, layer in results["layers"].items() if not layer["valid"]]
            results["error_summary"] = f"Failed layers: {', '.join(failed_layers)}"
        else:
            results["error_summary"] = "All layers passed"

        results["planner_feedback"] = self.build_planner_feedback(results)

        return results
