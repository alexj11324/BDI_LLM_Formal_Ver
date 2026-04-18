# Integration Guide: Current Mainline Verification

**Last Updated**: 2026-04-18  
**Purpose**: Practical guide for using the repository's current verification entrypoints and public helpers

---

## Overview

The current mainline runtime exposes three complementary verification layers:

1. **Structural verification** via `PlanVerifier`
2. **PDDL symbolic verification** via `PDDLSymbolicVerifier` and `VAL`
3. **Domain-specific checks** such as `BlocksworldPhysicsValidator`

For PDDL workloads, the repository now supports two primary CLI surfaces:

- `scripts/evaluation/run_generic_pddl_eval.py` for the generic mainline PDDL flow
- `scripts/evaluation/run_verification_only.py` for built-in-domain verification studies without repair

For code-level integrations, use:

- `from bdi_llm.planner import BDIPlanner`
- `from scripts.evaluation.planbench_utils import parse_pddl_problem, bdi_to_pddl_actions`

---

## Quick Start

### Run the generic mainline PDDL flow

```bash
# Single generic PDDL problem
python scripts/evaluation/run_generic_pddl_eval.py \
  --domain_pddl tests/fixtures/gripper/domain.pddl \
  --problem_pddl tests/fixtures/gripper/problem1.pddl

# Batch run with VAL verification
python scripts/evaluation/run_generic_pddl_eval.py \
  --domain_pddl tests/fixtures/gripper/domain.pddl \
  --problem_dir tests/fixtures/gripper \
  --execution_mode VERIFY_WITH_VAL
```

### Run verification-only analysis on built-in domains

```bash
python scripts/evaluation/run_verification_only.py --domain blocksworld --max_instances 10
python scripts/evaluation/run_verification_only.py --domain logistics --max_instances 10
python scripts/evaluation/run_verification_only.py --domain depots --max_instances 10
```

### Read a PDDL problem and inspect the extracted init state

```python
from scripts.evaluation.planbench_utils import parse_pddl_problem

pddl_data = parse_pddl_problem(
    "workspaces/planbench_data/plan-bench/instances/blocksworld/generated/instance-10.pddl"
)

print(pddl_data["problem_name"])
print(pddl_data["domain_name"])
print(pddl_data["init_state"])
```

---

## API Usage

### 1. Validate a blocksworld action list directly

```python
from bdi_llm.symbolic_verifier import BlocksworldPhysicsValidator

init_state = {
    "on_table": ["a", "b"],
    "on": [],
    "clear": ["a", "b"],
    "holding": None,
}

plan_actions = [
    "(pick-up a)",
    "(stack a b)",
]

validator = BlocksworldPhysicsValidator()
is_valid, errors = validator.validate_plan(plan_actions, init_state)

print(is_valid)
print(errors)
```

### 2. Generate a plan with `BDIPlanner` and build layered metrics

```python
from bdi_llm.planner import BDIPlanner
from bdi_llm.symbolic_verifier import BlocksworldPhysicsValidator
from bdi_llm.verifier import PlanVerifier
from scripts.evaluation.planbench_utils import bdi_to_pddl_actions

beliefs = (
    "Block a and block b are on the table. "
    "Block a is clear. Block b is clear. The hand is empty."
)
desire = "Block a is on block b."
init_state = {
    "on_table": ["a", "b"],
    "on": [],
    "clear": ["a", "b"],
    "holding": None,
}

planner = BDIPlanner(auto_repair=False, domain="blocksworld")
pred = planner.generate_plan(beliefs=beliefs, desire=desire)
plan = pred.plan

struct_result = PlanVerifier.verify(plan.to_networkx())
plan_actions = bdi_to_pddl_actions(plan, domain="blocksworld")
physics_valid, physics_errors = BlocksworldPhysicsValidator.validate_plan(
    plan_actions,
    init_state,
)

metrics = {
    "verification_layers": {
        "structural": {
            "valid": struct_result.is_valid,
            "errors": struct_result.errors,
            "hard_errors": struct_result.hard_errors,
            "warnings": struct_result.warnings,
        },
        "physics": {
            "valid": physics_valid,
            "errors": physics_errors,
        },
    },
    "overall_valid": struct_result.is_valid and physics_valid,
    "num_nodes": len(plan.nodes),
    "num_edges": len(plan.edges),
}

print(metrics["overall_valid"])
print(metrics["verification_layers"]["structural"]["valid"])
print(metrics["verification_layers"]["physics"]["valid"])
```

### 3. Convert a `BDIPlan` to PDDL actions

```python
from scripts.evaluation.planbench_utils import bdi_to_pddl_actions

pddl_actions = bdi_to_pddl_actions(plan, domain="blocksworld")
print(pddl_actions)
```

---

## Current Verification Flow

```text
PDDL problem file
    ↓
parse_pddl_problem()
    ↓
beliefs / desire / init_state
    ↓
BDIPlanner.generate_plan(...)
    ↓
BDIPlan
    ↓
PlanVerifier.verify(plan.to_networkx())
    ↓
bdi_to_pddl_actions(plan)
    ↓
BlocksworldPhysicsValidator.validate_plan(...)
    ↓
optional VAL verification in run_generic_pddl_eval.py
    ↓
layered metrics + run artifacts
```

---

## Testing

### Offline tests

```bash
# Physics validator
pytest tests/unit/test_symbolic_verifier.py -q

# Generic helper + planner integration
pytest tests/integration/test_generic_pddl_integration.py -q

# Blocksworld conversion / parser checks
pytest tests/integration/test_integration_phase2.py -q
```

### API-dependent tests

```bash
# Requires valid provider credentials
pytest tests/integration/test_integrated_verification.py -q
pytest tests/integration/test_integration.py -q
```

If provider credentials are missing or obviously fake, API-dependent tests should skip rather than hard-fail.

---

## Troubleshooting

### Problem: `init_state` is missing

Use the current parser helper and inspect the returned keys directly:

```python
from scripts.evaluation.planbench_utils import parse_pddl_problem

pddl_data = parse_pddl_problem("path/to/problem.pddl")
assert "init_state" in pddl_data
```

### Problem: physics validation always passes

Make sure you are validating the serialized PDDL action list, not the raw `BDIPlan` object:

```python
plan_actions = bdi_to_pddl_actions(plan, domain="blocksworld")
is_valid, errors = BlocksworldPhysicsValidator.validate_plan(plan_actions, init_state)
```

### Problem: generic planner raises missing `domain_context`

That error means you are using a generic PDDL domain without constructing a `DomainSpec` from the domain file. Use `run_generic_pddl_eval.py` or build a `DomainSpec.from_pddl(...)` before calling `BDIPlanner`.

---

## References

- [Functional Flow](FUNCTIONAL_FLOW.md)
- [Benchmarks](BENCHMARKS.md)
- [Technical Reference](TECHNICAL_REFERENCE.md)
- [README](../README.md)
