# Integration Guide: Multi-Layer Symbolic Verification

**Last Updated**: 2026-02-04
**Purpose**: Guide for using and understanding the integrated symbolic verification system

---

## Overview

The BDI-LLM framework now includes a **three-layer verification system** that validates plans at multiple levels of abstraction:

1. **Layer 1 - Structural Verification**: DAG properties (cycles, connectivity, topological ordering)
2. **Layer 2a - Physics Validation**: Domain-specific physical constraints (currently blocksworld)
3. **Layer 2b - PDDL Semantic Validation**: PDDL preconditions and goal achievement (VAL - Linux only)

---

## MCP Server Integration

The framework can be run as a Model Context Protocol (MCP) Server, allowing AI agents (like Claude Desktop) to use it as a native toolset.

### 1. Building the Docker Image
To ensure all dependencies (including the compiled VAL tool) are present, build the Docker image:

```bash
docker build -t bdi-verifier .
```

### 2. Running the Server
Run the container, passing your API key:

```bash
docker run -i --rm -e OPENAI_API_KEY=$OPENAI_API_KEY bdi-verifier
```

### 3. Exposed Tools
The server exposes the following tools to the agent:

*   **`generate_plan(beliefs, desire, domain)`**: Generates a BDI plan from natural language.
*   **`verify_plan(domain_pddl, problem_pddl, plan_actions)`**: Verifies a PDDL plan using the internal symbolic verifier.
*   **`execute_verified_plan(domain_pddl, problem_pddl, plan_actions, command_to_execute, rationale)`**:
    *   **"Trojan Horse" Pattern**: This tool acts as a secure gatekeeper.
    *   It first **verifies** the provided PDDL plan.
    *   **Only if verification passes** does it execute the `command_to_execute`.
    *   This allows agents to perform actions (like `cp`, `mv`, etc.) safely, ensuring the logical plan backing them is sound.

---

## Quick Start

### Running Multi-Layer Verification

```bash
# Run with physics validation on 3 instances
python run_planbench_full.py --domain blocksworld --max_instances 3

# Run full 100-instance benchmark
python run_planbench_full.py --domain blocksworld --max_instances 100
```

### Interpreting Results

The output will show comparative analysis:

```
--- Multi-Layer Verification Comparison ---
Structural-only success: 10 (33.3%)
Multi-layer success: 8 (26.7%)
Physics caught: 2 additional errors
```

**What this means:**
- **Structural-only success**: Plans that passed DAG validation (no cycles, connected graph)
- **Multi-layer success**: Plans that passed BOTH structural AND physics validation
- **Physics caught**: Additional errors found by physics validator that structural verification missed

---

## New Metrics Structure

### Before Integration

```python
{
    'generation_time': 1.23,
    'is_valid': True,
    'errors': [],
    'num_nodes': 5,
    'num_edges': 4
}
```

### After Integration

```python
{
    'generation_time': 1.23,
    'verification_layers': {
        'structural': {
            'valid': True,
            'errors': []
        },
        'physics': {
            'valid': True,
            'errors': []
        }
    },
    'overall_valid': True,  # structural AND physics
    'num_nodes': 5,
    'num_edges': 4
}
```

**Key Changes:**
- `verification_layers`: Separate results for each validation layer
- `overall_valid`: Combined validation result (must pass ALL layers)
- Backward compatible: Old keys (`num_nodes`, `num_edges`, `generation_time`) still present

---

## API Usage

### 1. Using BlocksworldPhysicsValidator Directly

```python
from src.bdi_llm.symbolic_verifier import BlocksworldPhysicsValidator

# Define initial state
init_state = {
    'on_table': ['a', 'b'],  # Blocks on table
    'on': [],                # (block1, block2) tuples
    'clear': ['a', 'b'],     # Clear blocks
    'holding': None          # Block in hand (or None)
}

# Define plan actions
plan = [
    "(pick-up a)",
    "(stack a b)"
]

# Validate
validator = BlocksworldPhysicsValidator()
is_valid, errors = validator.validate_plan(plan, init_state)

if is_valid:
    print("Plan is physically valid!")
else:
    print(f"Physics errors: {errors}")
```

### 2. Using Multi-Layer Verification in Plan Generation

```python
from run_planbench_full import generate_bdi_plan

# Generate plan with multi-layer verification
beliefs = "Block a and block b are on the table. Block a is clear. Block b is clear. The hand is empty."
desire = "Block a is on block b."

init_state = {
    'on_table': ['a', 'b'],
    'on': [],
    'clear': ['a', 'b'],
    'holding': None
}

plan, is_valid, metrics = generate_bdi_plan(beliefs, desire, init_state)

# Check results
print(f"Overall valid: {metrics['overall_valid']}")
print(f"Structural: {metrics['verification_layers']['structural']['valid']}")
print(f"Physics: {metrics['verification_layers']['physics']['valid']}")

if not is_valid:
    print("Errors:")
    for layer, data in metrics['verification_layers'].items():
        if not data['valid']:
            print(f"  {layer}: {data['errors']}")
```

### 3. Parsing PDDL with init_state Extraction

```python
from run_planbench_full import parse_pddl_problem

# Parse PDDL problem file
pddl_data = parse_pddl_problem('planbench_data/plan-bench/instances/blocksworld/generated/instance-10.pddl')

# Access init_state
init_state = pddl_data['init_state']
# Returns: {'on_table': [...], 'on': [...], 'clear': [...], 'holding': None}

# Also available:
# pddl_data['problem_name']
# pddl_data['objects']
# pddl_data['init']  # Raw PDDL predicates
# pddl_data['goal']
```

---

## Error Types

### Structural Errors (Layer 1)

```python
# Examples:
"Graph contains cycles: ['node1', 'node2', 'node1']"
"Graph is not weakly connected - found 2 disconnected components"
"Empty plan - no action nodes"
```

**Cause**: Invalid DAG structure
**Solution**: LLM needs to regenerate plan with proper dependencies

### Physics Errors (Layer 2a)

```python
# Examples:
"Cannot pick up block 'a' - it is not clear (has 'b' on top)"
"Cannot stack block 'a' - hand is empty"
"Cannot put down block 'a' on block 'b' - 'b' is not clear"
```

**Cause**: Violates blocksworld physical constraints
**Solution**: LLM needs to respect current state and physics rules

### PDDL Semantic Errors (Layer 2b - VAL)

```python
# Examples (when VAL is available):
"Action 'pick-up a' preconditions not satisfied"
"Goal state not achieved: (on a b) is false"
```

**Cause**: PDDL semantic violations
**Solution**: LLM needs to generate valid PDDL-compliant plans

---

## Verification Flow Diagram

```
PDDL Problem File
    ↓
parse_pddl_problem()
    ├─ objects: ['a', 'b', 'c']
    ├─ init: ['ontable a', 'clear a', ...]
    ├─ goal: ['on a b', 'on b c']
    └─ init_state: {'on_table': ['a'], ...}  ← NEW
    ↓
pddl_to_natural_language()
    ├─ beliefs: "Block a is on table..."
    └─ desire: "Block a is on block b..."
    ↓
generate_bdi_plan(beliefs, desire, init_state)
    ↓
    ├─ LLM generates BDIPlan
    ↓
    ├─ Layer 1: PlanVerifier.verify(graph)
    │   → structural validation result
    ↓
    ├─ bdi_to_pddl_actions(plan)
    │   → ["(pick-up a)", "(stack a b)"]
    ↓
    ├─ Layer 2a: BlocksworldPhysicsValidator.validate_plan(actions, init_state)
    │   → physics validation result
    ↓
    └─ Combine results
        → overall_valid = structural AND physics
```

---

## Testing

### Unit Tests (No API Key Required)

```bash
# Test physics validator
pytest tests/test_symbolic_verifier.py -v

# Test Phase 2 integration (offline)
python test_integration_phase2.py
```

### Integration Tests (Requires API Key)

```bash
# Set API key
export OPENAI_API_KEY="sk-..."

# Run integration tests
python test_integrated_verification.py

# Run small batch
python run_planbench_full.py --domain blocksworld --max_instances 3
```

---

## Known Limitations

### 1. Domain-Specific Physics Validation

**Current**: Only blocksworld is fully supported
**Workaround**: Physics validation skipped for other domains (falls back to structural only)

### 2. VAL Verifier Platform Dependency

**Issue**: VAL binary is Linux ELF format
**Status**: Not working on macOS
**Workaround**: Use physics validator (Layer 2a) instead
**Solution**: Recompile VAL for macOS or use Docker

### 3. API Key Required for Full Testing

**Offline tests**: Physics validator, PDDL parser, metrics structure
**Online tests**: Full LLM integration with plan generation
**Workaround**: Use provided test suite for offline validation

---

## Comparison with Previous System

| Aspect | Before Integration | After Integration |
|--------|-------------------|-------------------|
| **Validation Layers** | 1 (Structural only) | 2 (Structural + Physics) |
| **Error Detection** | DAG violations | DAG + Physical constraints |
| **Metrics** | Flat structure | Layered structure |
| **Success Rate** | ~67% (structural) | ~50-60% (multi-layer, stricter) |
| **Error Feedback** | Generic graph errors | Specific physics violations |

---

## Troubleshooting

### Problem: `init_state` is None

**Cause**: PDDL parser failed to extract initial state
**Check**:
```python
pddl_data = parse_pddl_problem('path/to/file.pddl')
if 'init_state' not in pddl_data:
    print("Parser missing init_state extraction")
```

### Problem: Physics validation always passes

**Cause**: `init_state` not provided to `generate_bdi_plan()`
**Solution**: Pass `init_state` parameter:
```python
plan, valid, metrics = generate_bdi_plan(beliefs, desire, init_state)
```

### Problem: Metrics missing `verification_layers`

**Cause**: Using old version of `generate_bdi_plan()`
**Check**: Verify function signature includes `init_state` parameter

---

## Next Steps

### For Researchers

1. **Run 100-instance benchmark** to get comprehensive statistics
2. **Analyze error distribution** across validation layers
3. **Compare success rates** before/after integration

### For Developers

1. **Implement feedback loop**: Pass physics errors back to LLM for auto-repair
2. **Add BDI consistency layer**: Validate Beliefs/Desires/Intentions coherence
3. **Fix VAL integration**: Recompile for macOS or containerize

---

## References

- **Architecture**: `docs/ARCHITECTURE.md`
- **Benchmarks**: `docs/BENCHMARKS.md`
- **Test Suite**: `tests/test_integrated_verification.py`, `tests/test_integration_phase2.py`
