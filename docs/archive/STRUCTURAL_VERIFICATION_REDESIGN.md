# Structural Verification Layer Redesign

**Date:** 2026-02-28
**Author:** Structural Verification Architect Team

## Executive Summary

After analyzing benchmark data from 2176 PlanBench instances across three domains, we found that **cycles should remain hard errors** in Layer 1 (structural verification). The data shows no evidence of cyclic plans successfully passing Layer 2 (VAL symbolic verification).

## Current Architecture

### Layer 1: Structural Verification (`src/bdi_llm/verifier.py`)

Current checks (hard + soft):
1. Empty graph check (line 19-21)
2. Weak connectivity check (warning only)
3. Cycle detection (line 30-36)
4. Topological sort feasibility (line 46-51)

### Layer 2: Symbolic Verification (`src/bdi_llm/symbolic_verifier.py`)

VAL validator checks:
- Preconditions satisfied at each step
- Effects correctly applied
- Goal state reachable
- Action parameters valid

### Layer 3: Domain Physics (`src/bdi_llm/symbolic_verifier.py:263-460`)

Domain-specific constraints (e.g., Blocksworld physics simulation)

## Data-Driven Analysis

### Cycle Statistics

| Dataset | Domain | Cycles Detected | Cycles Passing VAL | Success Despite Cycle |
|---------|--------|-----------------|-------------------|----------------------|
| ablation_BDI_ONLY | Blocksworld | 0 | 0 | 0 |
| ablation_BDI_ONLY | Logistics | 2 | 0 | 0 |
| ablation_BDI_ONLY | Depots | 0 | 0 | 0 |
| benchmark_gpt5_full | Logistics | 1 | 0 | 0 |

**Key Finding:** Zero cyclic plans passed VAL verification. This confirms that cycles represent genuine logical deadlocks, not false positives.

### Cycle Pattern Analysis

Examining detected cycles shows they are **true circular dependencies**, not parallel branches:

```
load_p3_into_a1_at_l1-1
  → fly_a1_l1-1_to_l0-1
  → unload_p3_from_a1_at_l0-1
  → drive_t0_l0-1_to_l0-4
  → ... (12 more actions) ...
  → drive_t1_l1-0_to_l1-1
  → unload_p3_from_t1_at_l1-1  # Returns to start location
```

This pattern indicates the LLM generated a plan where actions form a circular dependency chain - logically impossible to execute sequentially.

### NAIVE vs BDI_ONLY Gap Analysis

The observed gap between NAIVE (no verification) and BDI_ONLY (structural + symbolic) success rates is **NOT primarily caused by cycle rejections**:

| Domain | NAIVE Success | BDI_ONLY Success | Gap | Primary Gap Cause |
|--------|---------------|------------------|-----|-------------------|
| Blocksworld | 91.6% | ~90.8% | ~0.8% | API timeouts, not structural |
| Logistics | 68.7% | ~82.9% | N/A | BDI_ONLY actually HIGHER (repair helps) |
| Depots | 0% | ~99% | N/A | BDI_ONLY dramatically better |

The "31-35 instances" gap in blocksworld/logistics is due to **504 Gateway Timeout errors** during API calls, not structural verification false positives.

## Design Decision: Hard vs Soft Constraints

### Recommendation: Keep Cycles as HARD Errors

**Rationale:**
1. **Empirical evidence:** 0/3 cyclic plans passed VAL - cycles are genuine failures
2. **Theoretical basis:** A cycle in a dependency graph means no valid topological ordering exists - the plan cannot execute
3. **Repair mechanism:** The existing auto-repair system (`plan_repair.py`) can attempt to fix cyclic plans before rejection

### Proposed Hard vs Soft Classification

| Constraint | Classification | Rationale |
|------------|---------------|-----------|
| Empty graph | **HARD** | No plan generated |
| Missing nodes (dangling edges) | **HARD** | Malformed plan structure |
| Cycles | **HARD** | No valid execution order exists |
| Disconnected components | **SOFT → Warning** | May be parallel independent subplans |

## Implemented Changes (as of 2026-03-01)

### 1) `VerificationResult` introduced in `PlanVerifier`

```python
@dataclass
class VerificationResult:
    is_valid: bool
    hard_errors: List[str]
    warnings: List[str]

    @property
    def should_block_execution(self) -> bool:
        return len(self.hard_errors) > 0
```

Additionally, for compatibility with legacy call sites, the implementation provides:
- tuple-style unpacking (`is_valid, errors = PlanVerifier.verify(G)`)
- tuple-style indexing (`PlanVerifier.verify(G)[0]`)
- `errors` alias (`hard_errors + warnings`)

### 2) `verify()` now separates hard errors from warnings

```python
@staticmethod
def verify(graph: nx.DiGraph) -> VerificationResult:
    hard_errors = []
    warnings = []

    # HARD: Empty graph
    if graph.number_of_nodes() == 0:
        hard_errors.append("Plan is empty (no actions generated).")
        return VerificationResult(False, hard_errors, warnings)

    # SOFT: Disconnected components → warning only
    if not nx.is_weakly_connected(graph):
        warnings.append("Plan has disconnected components - may be parallel subplans")

    # HARD: Cycles
    try:
        cycles = list(nx.simple_cycles(graph))
        if cycles:
            for cycle in cycles:
                hard_errors.append(f"Cycle detected: {' -> '.join(cycle)}")
    except Exception as e:
        hard_errors.append(f"Error checking cycles: {str(e)}")

    is_valid = len(hard_errors) == 0
    return VerificationResult(is_valid, hard_errors, warnings)
```

### 3) `IntegratedVerifier.verify_full()` consumes structured results

```python
# Layer 1: Structural verification
G = bdi_plan.to_networkx()
struct_result = PlanVerifier.verify(G)

# Store warnings even if valid
results['layers']['structural'] = {
    'valid': struct_result.is_valid,
    'hard_errors': struct_result.hard_errors,
    'warnings': struct_result.warnings
}

# Continue to Layer 2 if no hard errors (even with warnings)
if struct_result.should_block_execution:
    # Skip Layer 2/3, trigger repair
    ...
else:
    # Proceed to VAL verification despite warnings
    symb_valid, symb_errors = self.symbolic_verifier.verify_plan(...)
```

### 4) `PlanRepairer` behavior aligned with warning-only connectivity

Even when Layer 1 marks a graph valid with disconnected warnings, `PlanRepairer.repair()` still performs connectivity repair (`_connect_subgraphs`) to preserve historical auto-repair behavior.

### 5) DFS cycle-breaker regression fixed

Cycle breaking now correctly pops recursion stack entries after DFS traversal, preventing accidental removal of non-cycle feeder edges.

### 6) Error reporting format

Separate warnings from errors in output:
```
=== Verification Report ===
Instance: logistics-042

Layer 1 (Structural): PASS with warnings
  Warnings:
    - Plan has disconnected components (possible parallel subplans)

Layer 2 (Symbolic): PASS
Layer 3 (Physics): PASS

Overall: VERIFIED
```

## Impact Assessment

### Expected Benefits

1. **Reduced false positives:** Disconnected but valid parallel plans won't be rejected
2. **Better diagnostics:** Clear separation of blocking errors vs warnings
3. **Improved repair targeting:** Repair focuses on hard errors only

### Risk Mitigation

1. **Cycles remain hard errors** - no risk of accepting logically impossible plans
2. **Disconnected components proceed to VAL** - VAL will catch any real execution issues
3. **Warnings logged for analysis** - can promote to hard errors if needed

## Ongoing Follow-ups

1. Monitor disconnected-component warning frequency in benchmark runs
2. Keep tuple compatibility until all external callers migrate to structured fields
3. Continue adding regression tests for repair edge cases

## Appendix: Sample Disconnected Plans

Parallel subplans that may legitimately be disconnected:
```
Subplan A (Truck delivery):    Subplan B (Airline delivery):
  load_t0_p1                     load_a0_p2
  drive_t0_l0-0_to_l0-1          fly_a0_l1-0_to_l2-0
  unload_t0_p1                   unload_a0_p2
```

These are independent and can execute in any interleaved order - should trigger warning, not failure.
