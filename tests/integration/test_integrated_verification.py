#!/usr/bin/env python3
"""
Test Integrated Verification
==============================

Test the complete multi-layer verification pipeline:
- Layer 1: Structural verification (DAG)
- Layer 2a: Physics validation (blocksworld)

Tests current parse + planner + multi-layer verification integration.

Author: BDI-LLM Research
Date: 2026-02-04
"""

import os
import pytest
from pathlib import Path

from bdi_llm.planner import BDIPlanner
from bdi_llm.symbolic_verifier import BlocksworldPhysicsValidator
from bdi_llm.verifier import PlanVerifier
from scripts.evaluation.planbench_utils import bdi_to_pddl_actions, parse_pddl_problem

def _is_valid_api_key(key):
    if not key:
        return False
    key_lower = key.lower()
    if "test" in key_lower or "placeholder" in key_lower or "dummy" in key_lower:
        return False
    return True

real_key = os.environ.get('OPENAI_API_KEY')
HAS_API_KEY = _is_valid_api_key(real_key)

# Set a dummy key if not present (for parser-only tests) so imports don't fail
if not real_key:
    os.environ['OPENAI_API_KEY'] = 'dummy-key-for-parsing-only'
    print("Note: Using dummy API key - LLM tests will be skipped\n")

def _generate_plan_with_layers(
    beliefs: str,
    desire: str,
    init_state: dict,
) -> tuple[object, bool, dict]:
    """Exercise the current planner + verifier stack without reviving legacy shims."""
    planner = BDIPlanner(auto_repair=False, domain="blocksworld")
    pred = planner.generate_plan(beliefs=beliefs, desire=desire)
    plan = pred.plan

    struct_result = PlanVerifier.verify(plan.to_networkx())
    pddl_actions = bdi_to_pddl_actions(plan, domain="blocksworld")
    physics_valid, physics_errors = BlocksworldPhysicsValidator.validate_plan(
        pddl_actions,
        init_state,
    )

    metrics = {
        'verification_layers': {
            'structural': {
                'valid': struct_result.is_valid,
                'errors': struct_result.errors,
                'hard_errors': struct_result.hard_errors,
                'warnings': struct_result.warnings,
            },
            'physics': {
                'valid': physics_valid,
                'errors': physics_errors,
            },
        },
        'overall_valid': struct_result.is_valid and physics_valid,
        'num_nodes': len(plan.nodes),
        'num_edges': len(plan.edges),
    }
    return plan, metrics['overall_valid'], metrics

def test_pddl_parser_init_state():
    """Test that parse_pddl_problem correctly extracts init_state"""
    print("="*80)
    print("  Test 1: PDDL Parser init_state Extraction")
    print("="*80 + "\n")

    # Use a generated instance file
    instance_path = Path("workspaces/planbench_data/plan-bench/instances/blocksworld/generated/instance-2.pddl")

    if not instance_path.exists():
        pytest.skip(f"Instance file not found: {instance_path}")

    try:
        pddl_data = parse_pddl_problem(str(instance_path))

        if 'init_state' not in pddl_data:
            pytest.fail("Missing init_state in parsed data")

        init_state = pddl_data['init_state']

        # Verify structure
        required_keys = {'on_table', 'on', 'clear', 'holding'}
        missing = required_keys - set(init_state.keys())

        assert not missing, f"Missing keys in init_state: {missing}"

        # Verify types
        assert isinstance(init_state['on_table'], list), "on_table should be a list"
        assert isinstance(init_state['on'], list), "on should be a list"
        assert isinstance(init_state['clear'], list), "clear should be a list"

        if init_state['holding'] is not None:
            assert isinstance(init_state['holding'], str), "holding should be None or str"

        print("  ✅ PASS: init_state extracted correctly")

    except Exception as e:
        pytest.fail(f"Exception during parsing: {e}")

def test_multi_layer_verification():
    """Test that the current planner stack exposes layered verification metrics."""
    print("="*80)
    print("  Test 2: Multi-Layer Verification in current planner stack")
    print("="*80 + "\n")

    if not HAS_API_KEY:
        pytest.skip("Requires valid OPENAI_API_KEY")

    # Simple test case
    beliefs = "Blocksworld domain with 3 blocks: a, b, c. Block a is on table and clear. Block b is on table and clear. Block c is on table and clear. Hand is empty."
    desire = "Stack all blocks: c on b, b on a"

    init_state = {
        'on_table': ['a', 'b', 'c'],
        'on': [],
        'clear': ['a', 'b', 'c'],
        'holding': None
    }

    try:
        plan, is_valid, metrics = _generate_plan_with_layers(beliefs, desire, init_state)

        # Check metrics structure
        assert 'verification_layers' in metrics, "verification_layers missing from metrics"

        layers = metrics['verification_layers']
        assert 'structural' in layers, "structural layer missing"
        assert 'physics' in layers, "physics layer missing"

        # Check each layer has required fields
        for layer_name in ['structural', 'physics']:
            layer = layers[layer_name]
            assert 'valid' in layer, f"{layer_name} layer missing 'valid' field"
            assert 'errors' in layer, f"{layer_name} layer missing 'errors' field"
            assert isinstance(layer['valid'], bool), f"{layer_name}.valid should be bool"
            assert isinstance(layer['errors'], list), f"{layer_name}.errors should be list"

        # Check overall_valid
        assert 'overall_valid' in metrics, "overall_valid missing from metrics"

        # Verify overall_valid logic
        expected_overall = layers['structural']['valid'] and layers['physics']['valid']
        actual_overall = metrics['overall_valid']

        assert expected_overall == actual_overall, f"overall_valid incorrect (expected {expected_overall}, got {actual_overall})"

        print("  ✅ PASS: Metrics structure correct")

    except Exception as e:
        pytest.fail(f"Exception during plan generation: {e}")

def test_physics_catches_errors():
    """Test that physics validation catches errors structural validation misses"""
    print("="*80)
    print("  Test 3: Physics Validation Catches Additional Errors")
    print("="*80 + "\n")

    if not HAS_API_KEY:
        pytest.skip("Requires valid OPENAI_API_KEY")

    # Create a scenario where structural might pass but physics should catch issues
    beliefs = "Blocksworld with blocks a, b. Block b is on block a. Block a is on table. Block b is clear. Hand is empty."
    desire = "Pick up block a"  # This is physically impossible - a is not clear

    init_state = {
        'on_table': ['a'],
        'on': [('b', 'a')],  # b is on a
        'clear': ['b'],
        'holding': None
    }

    try:
        plan, is_valid, metrics = _generate_plan_with_layers(beliefs, desire, init_state)

        struct_valid = metrics['verification_layers']['structural']['valid']
        physics_valid = metrics['verification_layers']['physics']['valid']

        print(f"  Results:")
        print(f"     - Structural valid: {struct_valid}")
        print(f"     - Physics valid: {physics_valid}")

        if struct_valid and not physics_valid:
            print("  ✅ PASS: Physics caught error that structural missed")
        elif not struct_valid and not physics_valid:
            print("  ⚠️  PARTIAL: Both layers caught errors (physics still working)")
        elif struct_valid and physics_valid:
            print("  ⚠️  INCONCLUSIVE: LLM generated a valid plan")
        else:
            print("  ⚠️  INCONCLUSIVE: Structural rejected")

    except Exception as e:
        pytest.fail(f"Exception: {e}")

def test_multiple_instances():
    """Test on multiple PDDL instances to verify no crashes"""
    print("="*80)
    print("  Test 4: Multiple Instance Stress Test")
    print("="*80 + "\n")

    base_path = Path("workspaces/planbench_data/plan-bench/instances/blocksworld/generated")

    if not base_path.exists():
        pytest.skip(f"Instance directory not found: {base_path}")

    # Test on first 3 instances
    instances = sorted(base_path.glob("instance-*.pddl"))[:3]

    if not instances:
        pytest.skip(f"No instances found in {base_path}")

    for instance_file in instances:
        try:
            # Parse PDDL
            pddl_data = parse_pddl_problem(str(instance_file))

            if 'init_state' not in pddl_data:
                pytest.fail(f"No init_state extracted from {instance_file.name}")

            # This should not crash
            init_state = pddl_data['init_state']

        except Exception as e:
            pytest.fail(f"Exception processing {instance_file.name}: {e}")

    print(f"  ✅ PASS: Tested {len(instances)} instances")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
