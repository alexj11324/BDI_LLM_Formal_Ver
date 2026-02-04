#!/usr/bin/env python3
"""
Test Phase 2 Integration - Physics Validation
==============================================

Tests the integration of BlocksworldPhysicsValidator into the pipeline
WITHOUT requiring LLM API access.

This tests:
1. BDI to PDDL action conversion
2. Physics validation with init_state
3. Layered metrics structure
"""

import sys
import os
from pathlib import Path

# Set dummy API key to avoid import errors
os.environ['OPENAI_API_KEY'] = 'test-key-for-imports'

sys.path.insert(0, str(Path(__file__).parent))

from src.bdi_llm.schemas import BDIPlan, ActionNode
from src.bdi_llm.symbolic_verifier import BlocksworldPhysicsValidator


def test_bdi_to_pddl_conversion():
    """Test converting BDI actions to PDDL format"""
    # Import the function from run_planbench_full
    from run_planbench_full import bdi_to_pddl_actions

    # Create a sample BDI plan
    plan = BDIPlan(
        goal_description="Stack blocks",
        nodes=[
            ActionNode(
                id="1",
                action_type="pick-up",
                params={"block": "a"},
                description="Pick up block a"
            ),
            ActionNode(
                id="2",
                action_type="stack",
                params={"block": "a", "target": "b"},
                description="Stack a on b"
            )
        ],
        edges=[]
    )

    # Convert to PDDL
    pddl_actions = bdi_to_pddl_actions(plan)

    print("Test 1: BDI to PDDL Conversion")
    print(f"  BDI Actions: {len(plan.nodes)}")
    print(f"  PDDL Actions: {pddl_actions}")

    # Verify
    assert len(pddl_actions) == 2, f"Expected 2 actions, got {len(pddl_actions)}"
    assert "(pick-up a)" in pddl_actions[0].lower(), f"Expected pick-up action, got {pddl_actions[0]}"
    assert "(stack a b)" in pddl_actions[1].lower(), f"Expected stack action, got {pddl_actions[1]}"

    print("  ✅ PASS\n")
    return True


def test_physics_validation_valid_plan():
    """Test physics validation with a valid plan"""

    init_state = {
        'on_table': ['a', 'b'],
        'on': [],
        'clear': ['a', 'b'],
        'holding': None
    }

    # Valid plan: pick up a, stack a on b
    pddl_actions = ["(pick-up a)", "(stack a b)"]

    validator = BlocksworldPhysicsValidator()
    is_valid, errors = validator.validate_plan(pddl_actions, init_state)

    print("Test 2: Physics Validation - Valid Plan")
    print(f"  Actions: {pddl_actions}")
    print(f"  Valid: {is_valid}")
    print(f"  Errors: {errors}")

    assert is_valid, f"Expected valid plan, got errors: {errors}"
    assert len(errors) == 0, f"Expected no errors, got: {errors}"

    print("  ✅ PASS\n")
    return True


def test_physics_validation_invalid_plan():
    """Test physics validation with an invalid plan"""

    init_state = {
        'on_table': ['a', 'b'],
        'on': [('c', 'a')],  # c is on a
        'clear': ['b', 'c'],
        'holding': None
    }

    # Invalid plan: try to pick up a (not clear - c is on top)
    pddl_actions = ["(pick-up a)"]

    validator = BlocksworldPhysicsValidator()
    is_valid, errors = validator.validate_plan(pddl_actions, init_state)

    print("Test 3: Physics Validation - Invalid Plan")
    print(f"  Actions: {pddl_actions}")
    print(f"  Init state: on(c, a), so 'a' is NOT clear")
    print(f"  Valid: {is_valid}")
    print(f"  Errors: {errors}")

    assert not is_valid, "Expected invalid plan"
    assert len(errors) > 0, "Expected error messages"
    assert any("not clear" in e.lower() for e in errors), f"Expected 'not clear' error, got: {errors}"

    print("  ✅ PASS\n")
    return True


def test_metrics_structure():
    """Test that metrics have the correct layered structure"""
    from run_planbench_full import parse_pddl_problem

    # Test with a real PDDL file
    test_file = "planbench_data/plan-bench/instances/blocksworld/generated/instance-10.pddl"

    if not Path(test_file).exists():
        print(f"Test 4: Metrics Structure - SKIPPED (test file not found)")
        return True

    pddl_data = parse_pddl_problem(test_file)

    print("Test 4: Metrics Structure")
    print(f"  PDDL file: {test_file}")
    print(f"  Has init_state: {'init_state' in pddl_data}")

    assert 'init_state' in pddl_data, "Expected init_state in pddl_data"

    init_state = pddl_data['init_state']
    print(f"  Init state keys: {list(init_state.keys())}")

    # Verify structure
    required_keys = ['on_table', 'on', 'clear', 'holding']
    for key in required_keys:
        assert key in init_state, f"Expected '{key}' in init_state"

    print("  ✅ PASS\n")
    return True


def main():
    """Run all tests"""
    print("="*80)
    print("  PHASE 2 INTEGRATION TESTS - Physics Validation")
    print("="*80)
    print()

    tests = [
        test_bdi_to_pddl_conversion,
        test_physics_validation_valid_plan,
        test_physics_validation_invalid_plan,
        test_metrics_structure
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}\n")
            failed += 1

    print("="*80)
    print(f"  RESULTS: {passed}/{len(tests)} tests passed")
    print("="*80)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
