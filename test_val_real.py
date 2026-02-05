#!/usr/bin/env python3
"""
Real VAL Test - Validate PDDL plan with actual VAL tool
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.bdi_llm.symbolic_verifier import PDDLSymbolicVerifier

# Files
domain_file = "planbench_data/plan-bench/pddlgenerators/blocksworld/domain.pddl"
problem_file = "planbench_data/plan-bench/instances/blocksworld/generated/instance-10.pddl"

verifier = PDDLSymbolicVerifier()

print("="*80)
print("  VAL Symbolic Verification Test")
print("="*80 + "\n")

print(f"Domain: {domain_file}")
print(f"Problem: {problem_file}\n")

# Test 1: Correct plan for instance-10
# instance-10: 5 blocks (d, e, a, b, f), Goal: d on e on a on b on f
print("Test 1: Correct Plan")
correct_plan = [
    "(pickup f)",
    "(stack f b)",
    "(pickup b)",
    "(stack b a)",
    "(pickup a)",
    "(stack a e)",
    "(pickup e)",
    "(stack e d)"
]

print(f"Actions: {len(correct_plan)}")
for i, action in enumerate(correct_plan, 1):
    print(f"  {i}. {action}")
print()

is_valid, errors = verifier.verify_plan(domain_file, problem_file, correct_plan, verbose=False)

if is_valid:
    print("✅ VAL PASSED: Plan is valid!\n")
else:
    print("❌ VAL FAILED:")
    for err in errors:
        print(f"   {err}")
    print()

# Test 2: Incorrect plan (violates preconditions)
print("Test 2: Incorrect Plan (violates preconditions)")
incorrect_plan = [
    "(pickup d)",  # ERROR: d might not be on table initially
    "(stack d e)"
]

print(f"Actions: {len(incorrect_plan)}")
for i, action in enumerate(incorrect_plan, 1):
    print(f"  {i}. {action}")
print()

is_valid, errors = verifier.verify_plan(domain_file, problem_file, incorrect_plan, verbose=True)

if is_valid:
    print("✅ VAL PASSED (unexpected!)\n")
else:
    print("❌ VAL FAILED (expected):")
    for err in errors:
        print(f"   {err}")
    print()

print("="*80)
print("  VAL Test Complete")
print("="*80)
