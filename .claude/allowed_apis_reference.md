# Allowed APIs Reference - Symbolic Verification Integration

**Generated**: 2026-02-04
**Purpose**: API documentation for Phase 1-6 implementation

---

## 1. Existing Structural Verifier

**File**: `src/bdi_llm/verifier.py`

```python
from src.bdi_llm.verifier import PlanVerifier

# Signature
PlanVerifier.verify(graph: nx.DiGraph) -> Tuple[bool, List[str]]

# Usage (from run_planbench_full.py:188-189)
G = plan.to_networkx()
is_valid, errors = PlanVerifier.verify(G)
```

**Returns**: `(is_valid: bool, errors: List[str])`

---

## 2. New Symbolic Verifier - BlocksworldPhysicsValidator

**File**: `src/bdi_llm/symbolic_verifier.py`

```python
from src.bdi_llm.symbolic_verifier import BlocksworldPhysicsValidator

# Signature
BlocksworldPhysicsValidator.validate_plan(
    plan_actions: List[str],
    init_state: Dict
) -> Tuple[bool, List[str]]

# Required init_state structure (from test_symbolic_verifier.py:36-41)
init_state = {
    'on_table': ['a', 'b'],      # List of blocks on table
    'on': [('a', 'b')],           # List of tuples (block_from, block_to)
    'clear': ['a', 'b'],          # List of clear blocks
    'holding': None               # None or block name
}

# Example usage (from test_symbolic_verifier.py:43-45)
validator = BlocksworldPhysicsValidator()
plan_actions = ["(pick-up a)", "(stack a b)"]
is_valid, errors = validator.validate_plan(plan_actions, init_state)
```

**Returns**: `(is_valid: bool, errors: List[str])`

---

## 3. PDDL Parser

**File**: `run_planbench_full.py`

**Current function** (lines 44-78):
```python
def parse_pddl_problem(pddl_file: str) -> dict:
    # Returns:
    # {
    #     'problem_name': str,
    #     'objects': List[str],
    #     'init': List[str],      # e.g., ['ontable a', 'clear a', ...]
    #     'goal': List[str]
    # }
```

**Predicates in init** (blocksworld):
- `ontable <block>` - block is on table
- `clear <block>` - nothing on top of block
- `on <block1> <block2>` - block1 is on block2
- `handempty` - hand is empty
- `holding <block>` - hand holds block

**Required modification**: Add `init_state` key to return dict

---

## 4. BDI Plan Generation

**File**: `run_planbench_full.py`

**Current function** (lines 168-204):
```python
def generate_bdi_plan(beliefs: str, desire: str, timeout: int = 60) -> Tuple[BDIPlan, bool, dict]:
    planner = BDIPlanner()
    result = planner.generate_plan(beliefs=beliefs, desire=desire)
    plan = result.plan

    # Structural verification (line 188-189)
    G = plan.to_networkx()
    is_valid, errors = PlanVerifier.verify(G)

    # Current metrics (lines 173-179)
    metrics = {
        'generation_time': float,
        'is_valid': bool,
        'errors': List[str],
        'num_nodes': int,
        'num_edges': int
    }

    return plan, is_valid, metrics
```

**Required modification**: Add physics validation after structural validation

---

## 5. DAG to PDDL Conversion

**Not yet in codebase** - Need to implement or identify

**Pattern needed**:
```python
def dag_to_pddl_plan(plan: BDIPlan) -> List[str]:
    """Convert BDI action nodes to PDDL action strings"""
    # Example:
    # ActionNode(id="1", type="pick-up", params={"block": "a"})
    # -> "(pick-up a)"
    return pddl_actions
```

---

## 6. Anti-Patterns (PROHIBITED)

### ❌ DO NOT use PDDLSymbolicVerifier (VAL)
**Reason**: VAL is Linux ELF binary, incompatible with macOS
**Source**: docs/SYMBOLIC_VERIFICATION_STATUS.md:50-87

```python
# ❌ PROHIBITED
from src.bdi_llm.symbolic_verifier import PDDLSymbolicVerifier
verifier = PDDLSymbolicVerifier()  # Will fail on macOS
```

### ❌ DO NOT modify existing return keys
**Reason**: Breaks backward compatibility
**Instead**: Add new keys, keep old ones

### ❌ DO NOT assume init_state always has all keys
**Solution**: Use defensive `.get()` with defaults

```python
# ✅ CORRECT
on_table = init_state.get('on_table', [])
holding = init_state.get('holding', None)

# ❌ WRONG
on_table = init_state['on_table']  # KeyError if missing
```

---

## 7. Integration Points

**File**: `run_planbench_full.py`

**Line 44-78**: `parse_pddl_problem()` - Add init_state extraction
**Line 168-204**: `generate_bdi_plan()` - Add physics validation
**Line 173-179**: `metrics` dict - Expand to layered structure
**Line 296**: `instance_result['success']` - Use overall_valid

---

## 8. Data Flow

```
PDDL File
  ↓
parse_pddl_problem() → {objects, init, goal, init_state}
  ↓
pddl_to_natural_language() → (beliefs, desire)
  ↓
generate_bdi_plan() → (BDIPlan, is_valid, metrics)
  ├─ Structural: PlanVerifier.verify(G)
  ├─ DAG→PDDL: dag_to_pddl_plan(plan)
  └─ Physics: BlocksworldPhysicsValidator.validate_plan(pddl_actions, init_state)
  ↓
overall_valid = structural AND physics
```

---

## 9. Required New Metrics Structure

```python
metrics = {
    'generation_time': float,
    'verification_layers': {
        'structural': {'valid': bool, 'errors': List[str]},
        'physics': {'valid': bool, 'errors': List[str]}
    },
    'overall_valid': bool,  # structural AND physics
    'num_nodes': int,
    'num_edges': int
}
```

---

## Phase 0 Complete ✅

All APIs documented with exact signatures and usage patterns.
