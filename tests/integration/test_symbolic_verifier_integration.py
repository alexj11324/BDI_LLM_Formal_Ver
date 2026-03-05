#!/usr/bin/env python3
"""
Test Symbolic Verifier
======================

Test the PDDL symbolic verification layer.

Author: BDI-LLM Research
Date: 2026-02-03
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.bdi_llm.symbolic_verifier import (
    PDDLSymbolicVerifier,
    BlocksworldPhysicsValidator
)


def test_physics_validator():
    """Test blocksworld physics validation"""
    print("="*80)
    print("  Testing Blocksworld Physics Validator")
    print("="*80 + "\n")

    validator = BlocksworldPhysicsValidator()

    # Test Case 1: Valid plan
    print("Test 1: Valid Plan")
    print("  Initial: A, B on table (both clear), hand empty")
    print("  Plan: pick-up(a), stack(a, b)")

    init_state = {
        'on_table': ['a', 'b'],
        'on': [],
        'clear': ['a', 'b'],
        'holding': None
    }

    valid_plan = ["(pick-up a)", "(stack a b)"]

    is_valid, errors = validator.validate_plan(valid_plan, init_state)

    if is_valid:
        print("  ✅ VALID\n")
    else:
        print("  ❌ INVALID:")
        for err in errors:
            print(f"     {err}")
        print()

    # Test Case 2: Invalid - pick up non-clear block
    print("Test 2: Invalid - Pick up non-clear block")
    print("  Initial: A on B, B on table, A clear, hand empty")
    print("  Plan: pick-up(b)  ← ERROR: B not clear")

    init_state_2 = {
        'on_table': ['b'],
        'on': [('a', 'b')],
        'clear': ['a'],
        'holding': None
    }

    invalid_plan = ["(pick-up b)"]

    is_valid, errors = validator.validate_plan(invalid_plan, init_state_2)

    if is_valid:
        print("  ✅ VALID (unexpected!)\n")
    else:
        print("  ❌ INVALID (expected):")
        for err in errors:
            print(f"     {err}")
        print()

    # Test Case 3: Invalid - hand not empty
    print("Test 3: Invalid - Hand not empty")
    print("  Initial: A on table (clear), hand holding B")
    print("  Plan: pick-up(a)  ← ERROR: hand already holding B")

    init_state_3 = {
        'on_table': ['a'],
        'on': [],
        'clear': ['a'],
        'holding': 'b'
    }

    invalid_plan_2 = ["(pick-up a)"]

    is_valid, errors = validator.validate_plan(invalid_plan_2, init_state_3)

    if is_valid:
        print("  ✅ VALID (unexpected!)\n")
    else:
        print("  ❌ INVALID (expected):")
        for err in errors:
            print(f"     {err}")
        print()

    print("="*80)
    print("  Physics Validator Test Complete")
    print("="*80 + "\n")


def test_val_verifier():
    """Test VAL-based symbolic verifier"""
    print("="*80)
    print("  Testing VAL Symbolic Verifier")
    print("="*80 + "\n")

    try:
        verifier = PDDLSymbolicVerifier()
        print(f"✅ VAL verifier initialized")
        print(f"   VAL path: {verifier.val_path}\n")

        # Check if we have PlanBench data
        planbench_base = Path("planbench_data/plan-bench")
        if not planbench_base.exists():
            print("⚠️  PlanBench data not found - skipping VAL tests")
            print(f"   Expected at: {planbench_base.absolute()}\n")
            return

        # Test on instance-10 (known to be simple)
        domain_file = planbench_base / "instances/blocksworld/domain.pddl"
        problem_file = planbench_base / "instances/blocksworld/generated/instance-10.pddl"

        if not domain_file.exists() or not problem_file.exists():
            print(f"⚠️  Domain/problem files not found:")
            print(f"   Domain: {domain_file}")
            print(f"   Problem: {problem_file}\n")
            return

        print(f"Test: Validating a simple blocksworld plan")
        print(f"  Domain: {domain_file.name}")
        print(f"  Problem: {problem_file.name}")

        # Simple plan for instance-10 (5 blocks: d, e, a, b, f)
        # Goal: d on e, e on a, a on b, b on f
        simple_plan = [
            "(pick-up d)",
            "(stack d e)",
            "(pick-up e)",
            "(stack e a)",
            "(pick-up a)",
            "(stack a b)",
            "(pick-up b)",
            "(stack b f)"
        ]

        print(f"  Plan: {len(simple_plan)} actions\n")

        is_valid, errors = verifier.verify_plan(
            str(domain_file),
            str(problem_file),
            simple_plan,
            verbose=True
        )

        if is_valid:
            print("  ✅ VAL VALIDATION PASSED\n")
        else:
            print("  ❌ VAL VALIDATION FAILED:")
            for err in errors:
                print(f"     {err}")
            print()

    except FileNotFoundError as e:
        print(f"⚠️  {e}\n")
    except Exception as e:
        print(f"❌ Error: {e}\n")

    print("="*80)
    print("  VAL Verifier Test Complete")
    print("="*80 + "\n")


if __name__ == "__main__":
    # Test physics validator (no dependencies)
    test_physics_validator()

    # Test VAL verifier (requires PlanBench + VAL)
    test_val_verifier()
