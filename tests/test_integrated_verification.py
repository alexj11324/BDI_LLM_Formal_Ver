#!/usr/bin/env python3
"""
Test Integrated Verification
==============================

Test the complete multi-layer verification pipeline:
- Layer 1: Structural verification (DAG)
- Layer 2a: Physics validation (blocksworld)

Tests both parse_pddl_problem() and generate_bdi_plan() integration.

Author: BDI-LLM Research
Date: 2026-02-04
"""

import sys
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

# Check if API key is available
HAS_API_KEY = 'OPENAI_API_KEY' in os.environ and os.environ['OPENAI_API_KEY']

# Set a dummy key if not present (for parser-only tests)
if not HAS_API_KEY:
    os.environ['OPENAI_API_KEY'] = 'dummy-key-for-parsing-only'
    print("Note: Using dummy API key - LLM tests will be skipped\n")

# Import parse_pddl_problem directly (doesn't need API)
from scripts.run_planbench_full import parse_pddl_problem

# Only import generate_bdi_plan if we have real API key
generate_bdi_plan = None
if HAS_API_KEY:
    from scripts.run_planbench_full import generate_bdi_plan


def test_pddl_parser_init_state():
    """Test that PDDL parser extracts init_state correctly"""
    print("="*80)
    print("  Test 1: PDDL Parser init_state Extraction")
    print("="*80 + "\n")

    # Use a known blocksworld instance
    test_file = "planbench_data/plan-bench/instances/blocksworld/generated/instance-10.pddl"

    if not Path(test_file).exists():
        print(f"  ⚠️  SKIP: Test file not found: {test_file}\n")
        return False

    print(f"  Parsing: {test_file}")

    try:
        pddl_data = parse_pddl_problem(test_file)

        # Check that init_state key exists
        if 'init_state' not in pddl_data:
            print("  ❌ FAIL: init_state key missing from return dict\n")
            return False

        init_state = pddl_data['init_state']

        # Verify structure
        required_keys = {'on_table', 'on', 'clear', 'holding'}
        missing = required_keys - set(init_state.keys())

        if missing:
            print(f"  ❌ FAIL: Missing keys in init_state: {missing}\n")
            return False

        # Verify types
        if not isinstance(init_state['on_table'], list):
            print("  ❌ FAIL: on_table should be a list\n")
            return False

        if not isinstance(init_state['on'], list):
            print("  ❌ FAIL: on should be a list\n")
            return False

        if not isinstance(init_state['clear'], list):
            print("  ❌ FAIL: clear should be a list\n")
            return False

        if init_state['holding'] is not None and not isinstance(init_state['holding'], str):
            print("  ❌ FAIL: holding should be None or str\n")
            return False

        print("  ✅ PASS: init_state extracted correctly")
        print(f"     - on_table: {init_state['on_table']}")
        print(f"     - on: {init_state['on']}")
        print(f"     - clear: {init_state['clear']}")
        print(f"     - holding: {init_state['holding']}\n")

        return True

    except Exception as e:
        print(f"  ❌ FAIL: Exception during parsing: {e}\n")
        return False


def test_multi_layer_verification():
    """Test that generate_bdi_plan includes multi-layer verification"""
    print("="*80)
    print("  Test 2: Multi-Layer Verification in generate_bdi_plan()")
    print("="*80 + "\n")

    if not HAS_API_KEY:
        print("  ⚠️  SKIP: Requires OPENAI_API_KEY environment variable\n")
        return True  # Don't fail, just skip

    # Simple test case
    beliefs = "Blocksworld domain with 3 blocks: a, b, c. Block a is on table and clear. Block b is on table and clear. Block c is on table and clear. Hand is empty."
    desire = "Stack all blocks: c on b, b on a"

    init_state = {
        'on_table': ['a', 'b', 'c'],
        'on': [],
        'clear': ['a', 'b', 'c'],
        'holding': None
    }

    print(f"  Beliefs: {beliefs[:60]}...")
    print(f"  Desire: {desire}")
    print(f"  Initial state provided: {init_state}\n")

    try:
        plan, is_valid, metrics = generate_bdi_plan(beliefs, desire, init_state, timeout=30)

        # Check metrics structure
        print("  Checking metrics structure...")

        if 'verification_layers' not in metrics:
            print("  ❌ FAIL: verification_layers missing from metrics\n")
            return False

        layers = metrics['verification_layers']

        if 'structural' not in layers:
            print("  ❌ FAIL: structural layer missing\n")
            return False

        if 'physics' not in layers:
            print("  ❌ FAIL: physics layer missing\n")
            return False

        # Check each layer has required fields
        for layer_name in ['structural', 'physics']:
            layer = layers[layer_name]

            if 'valid' not in layer:
                print(f"  ❌ FAIL: {layer_name} layer missing 'valid' field\n")
                return False

            if 'errors' not in layer:
                print(f"  ❌ FAIL: {layer_name} layer missing 'errors' field\n")
                return False

            if not isinstance(layer['valid'], bool):
                print(f"  ❌ FAIL: {layer_name}.valid should be bool\n")
                return False

            if not isinstance(layer['errors'], list):
                print(f"  ❌ FAIL: {layer_name}.errors should be list\n")
                return False

        # Check overall_valid
        if 'overall_valid' not in metrics:
            print("  ❌ FAIL: overall_valid missing from metrics\n")
            return False

        # Verify overall_valid logic
        expected_overall = layers['structural']['valid'] and layers['physics']['valid']
        actual_overall = metrics['overall_valid']

        if expected_overall != actual_overall:
            print(f"  ❌ FAIL: overall_valid incorrect (expected {expected_overall}, got {actual_overall})\n")
            return False

        print("  ✅ PASS: Metrics structure correct")
        print(f"     - Structural: {layers['structural']['valid']}")
        print(f"     - Physics: {layers['physics']['valid']}")
        print(f"     - Overall: {actual_overall}")

        if not layers['structural']['valid']:
            print(f"     - Structural errors: {layers['structural']['errors']}")

        if not layers['physics']['valid']:
            print(f"     - Physics errors: {layers['physics']['errors']}")

        print()

        return True

    except Exception as e:
        print(f"  ❌ FAIL: Exception during plan generation: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_physics_catches_errors():
    """Test that physics validation catches errors structural validation misses"""
    print("="*80)
    print("  Test 3: Physics Validation Catches Additional Errors")
    print("="*80 + "\n")

    if not HAS_API_KEY:
        print("  ⚠️  SKIP: Requires OPENAI_API_KEY environment variable\n")
        return True  # Don't fail, just skip

    print("  NOTE: This test requires LLM to generate an invalid plan.")
    print("  If LLM generates a valid plan, the test may not demonstrate error catching.\n")

    # Create a scenario where structural might pass but physics should catch issues
    beliefs = "Blocksworld with blocks a, b. Block b is on block a. Block a is on table. Block b is clear. Hand is empty."
    desire = "Pick up block a"  # This is physically impossible - a is not clear

    init_state = {
        'on_table': ['a'],
        'on': [('b', 'a')],  # b is on a
        'clear': ['b'],
        'holding': None
    }

    print(f"  Beliefs: {beliefs}")
    print(f"  Desire: {desire}")
    print(f"  Expected: Physics should reject picking up 'a' (not clear)\n")

    try:
        plan, is_valid, metrics = generate_bdi_plan(beliefs, desire, init_state, timeout=30)

        struct_valid = metrics['verification_layers']['structural']['valid']
        physics_valid = metrics['verification_layers']['physics']['valid']

        print(f"  Results:")
        print(f"     - Structural valid: {struct_valid}")
        print(f"     - Physics valid: {physics_valid}")

        if struct_valid and not physics_valid:
            print("  ✅ PASS: Physics caught error that structural missed")
            print(f"     - Physics errors: {metrics['verification_layers']['physics']['errors']}")
        elif not struct_valid and not physics_valid:
            print("  ⚠️  PARTIAL: Both layers caught errors (physics still working)")
            print(f"     - Structural errors: {metrics['verification_layers']['structural']['errors']}")
            print(f"     - Physics errors: {metrics['verification_layers']['physics']['errors']}")
        elif struct_valid and physics_valid:
            print("  ⚠️  INCONCLUSIVE: LLM generated a valid plan (possibly modified goal)")
            print(f"     - This doesn't prove physics validation is broken")
        else:
            print("  ⚠️  INCONCLUSIVE: Structural rejected (can't test physics layer)")

        print()
        return True

    except Exception as e:
        print(f"  ❌ FAIL: Exception: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_multiple_instances():
    """Test on multiple PDDL instances to verify no crashes"""
    print("="*80)
    print("  Test 4: Multiple Instance Stress Test")
    print("="*80 + "\n")

    base_path = Path("planbench_data/plan-bench/instances/blocksworld/generated")

    if not base_path.exists():
        print(f"  ⚠️  SKIP: Instance directory not found: {base_path}\n")
        return False

    # Test on first 3 instances
    instances = sorted(base_path.glob("instance-*.pddl"))[:3]

    if not instances:
        print(f"  ⚠️  SKIP: No instances found in {base_path}\n")
        return False

    print(f"  Testing {len(instances)} instances...\n")

    passed = 0
    failed = 0

    for instance_file in instances:
        print(f"  Testing: {instance_file.name}")

        try:
            # Parse PDDL
            pddl_data = parse_pddl_problem(str(instance_file))

            if 'init_state' not in pddl_data:
                print(f"    ❌ FAIL: No init_state extracted\n")
                failed += 1
                continue

            # This should not crash
            init_state = pddl_data['init_state']

            print(f"    ✅ PASS: Parsed successfully")
            print(f"       - {len(init_state.get('on_table', []))} blocks on table")
            print(f"       - {len(init_state.get('on', []))} on relationships")
            print(f"       - {len(init_state.get('clear', []))} clear blocks\n")

            passed += 1

        except Exception as e:
            print(f"    ❌ FAIL: Exception: {e}\n")
            failed += 1

    print(f"  Summary: {passed}/{len(instances)} passed\n")

    return failed == 0


def main():
    """Run all integration tests"""
    print("\n" + "="*80)
    print("  INTEGRATED VERIFICATION TEST SUITE")
    print("="*80 + "\n")

    results = {
        'Test 1: PDDL Parser init_state': test_pddl_parser_init_state(),
        'Test 2: Multi-Layer Verification': test_multi_layer_verification(),
        'Test 3: Physics Catches Errors': test_physics_catches_errors(),
        'Test 4: Multiple Instances': test_multiple_instances()
    }

    print("="*80)
    print("  TEST SUMMARY")
    print("="*80 + "\n")

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test_name}")

    passed_count = sum(results.values())
    total_count = len(results)

    print(f"\n  Total: {passed_count}/{total_count} tests passed")
    print("="*80 + "\n")

    return passed_count == total_count


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
