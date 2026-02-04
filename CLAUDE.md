# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**BDI-LLM Formal Verification Framework** - A research prototype that combines LLM-generated BDI (Belief-Desire-Intention) planning with formal graph-theoretic verification. The system uses Claude Opus 4 via DSPy to generate structured action plans, then validates them using NetworkX-based DAG verification.

**Core Innovation**: Uses a formal verifier as a "compiler" to catch structural errors in LLM-generated plans, demonstrating LLM + Formal Methods integration.

## Architecture

### Pipeline Flow
```
User Input (Beliefs + Desire)
    ↓
DSPy LLM Planner (src/bdi_llm/planner.py) → Generates BDIPlan
    ↓
Pydantic Schema Validation (src/bdi_llm/schemas.py) → ActionNodes + DependencyEdges
    ↓
NetworkX DiGraph Conversion → Graph representation
    ↓
Formal Verifier (src/bdi_llm/verifier.py) → DAG validation
    ├─ Cycle Detection (deadlock prevention)
    ├─ Connectivity Check (no disconnected subgraphs)
    └─ Topological Sort (execution order)
    ↓
Valid Plan + Execution Order | Error Feedback
```

### Core Components

**src/bdi_llm/schemas.py**: Pydantic models defining the plan structure
- `ActionNode`: Atomic action with id, type, params, description
- `DependencyEdge`: Directed edge representing "source must complete before target"
- `BDIPlan`: Complete plan with goal, nodes, edges, and `.to_networkx()` converter

**src/bdi_llm/verifier.py**: Graph-theoretic formal verifier
- Checks: Empty plans, weak connectivity, cycles (DAG requirement)
- Returns: (is_valid, error_list) tuple
- Uses NetworkX's `is_weakly_connected()` and `simple_cycles()`

**src/bdi_llm/planner.py**: DSPy-powered LLM planner
- Uses `dspy.TypedPredictor` with Pydantic schema enforcement
- Contains `dspy.Assert()` for self-correction on verification failures
- Configured for CMU AI Gateway (Claude Opus 4)

**src/bdi_llm/visualizer.py**: NetworkX-based plan visualization
- Kamada-Kawai layout for DAG visualization
- Color-coded by action type
- Annotates execution order and validation errors

**run_evaluation.py**: Multi-mode evaluation framework
- Modes: unit tests, offline demo, LLM demo, benchmark
- No API key needed for unit tests and offline demo

## Common Development Commands

### Running Tests

```bash
# Unit tests only (no API key required)
python run_evaluation.py --mode unit
# or directly:
pytest tests/test_verifier.py -v

# Offline demo (no API key, shows verifier capabilities)
python run_evaluation.py --mode demo-offline

# Full LLM integration test (requires API key)
export OPENAI_API_KEY=sk-...  # CMU AI Gateway key
python run_evaluation.py --mode demo

# Run full benchmark suite
python run_evaluation.py --mode benchmark

# Run everything
python run_evaluation.py --mode all
```

### Running Individual Components

```bash
# Run planner standalone
python -m src.bdi_llm.planner

# Generate visualization
python -m src.bdi_llm.visualizer

# Run specific test file
pytest tests/test_integration.py -v
```

## API Configuration

The codebase uses **CMU AI Gateway** for Claude Opus 4 access:

```python
os.environ["OPENAI_API_KEY"] = "REDACTED_OPENAI_KEY"
os.environ["OPENAI_API_BASE"] = "https://ai-gateway.andrew.cmu.edu/v1"
lm = dspy.LM(model="openai/claude-opus-4-20250514-v1:0", ...)
```

**Important**: The API key in `src/bdi_llm/planner.py` is hardcoded for the CMU Gateway. If modifying API configuration, update both environment variables and the DSPy LM initialization.

## Known Issues & Design Constraints

### Parallel Task Handling (Critical)

**Problem**: LLM generates disconnected subgraphs for parallel scenarios (see docs/PARALLEL_FAILURE_ANALYSIS.md)

**Example Failure**: "Print document and send email simultaneously" → Two independent islands with no connecting edges

**Root Cause**:
- LLM interprets "parallel" as completely independent tasks
- Lacks understanding of graph connectivity constraints
- Does not create fork-join patterns (diamond structure) automatically

**Correct Structure Required**:
```python
# For parallel tasks A and B followed by C:
nodes: [START, A, B, C]
edges: [START→A, START→B, A→C, B→C]  # Fork-join pattern
```

**Future Fix Options**:
1. Enhanced prompt with explicit fork-join examples
2. Post-processing to auto-insert virtual START/END nodes
3. DSPy few-shot examples for parallel scenarios

### DSPy 3.x Compatibility

The codebase uses DSPy's `dspy.Assert()` for self-correction during inference. Note:
- DSPy 3.x has limited self-correction compared to 2.x
- Optimization features (MIPRO) require dataset collection
- Current implementation relies on assertion-based retry

## Graph Theory Requirements

Plans MUST satisfy these formal properties:

1. **DAG (Directed Acyclic Graph)**: No cycles allowed (prevents deadlocks)
2. **Weak Connectivity**: All nodes reachable when ignoring edge direction
3. **Non-empty**: At least one action node

The verifier enforces these via:
- `nx.is_weakly_connected(G)` → Ensures no disconnected components
- `nx.simple_cycles(G)` → Detects circular dependencies
- `nx.topological_sort(G)` → Generates execution order (only possible for DAGs)

## Test Coverage & Benchmarks

**Current Metrics** (see docs/EVALUATION_REPORT.md):
- Unit tests: 11/11 (100%)
- Offline demo: 3/3 (100%)
- LLM integration: 1/1 (100%)
- Benchmark: 3/4 (75%) - Parallel task scenario fails

**Test Organization**:
- `tests/test_verifier.py`: Graph verification unit tests (no API)
- `tests/test_integration.py`: Full pipeline with LLM (requires API)

## File Naming & Conventions

- All visualization outputs use `.png` extension
- Benchmark results saved to `benchmark_results.json`
- Analysis documents use `_ANALYSIS.md` suffix
- Test files follow `test_*.py` naming

## Modifying the Prompt

The LLM prompt is in `src/bdi_llm/planner.py` → `GeneratePlan` signature docstring. When modifying:

1. Keep the Pydantic schema structure explicit
2. Add graph constraints if addressing parallel task issues
3. Test with `--mode demo` before running benchmark
4. Consider adding few-shot examples via DSPy's `dspy.Example()`

Example of adding connectivity constraint:
```python
class GeneratePlan(dspy.Signature):
    """
    ... existing instructions ...

    CRITICAL: The plan graph MUST be weakly connected.
    For parallel tasks, use a fork-join pattern with shared start/end nodes.
    """
```

## Dependencies

Core libraries:
- `dspy` - LLM structured output and self-correction
- `pydantic` - Schema validation
- `networkx` - Graph algorithms and verification
- `matplotlib` - Visualization
- `pytest` - Testing framework

The framework is model-agnostic (works with any DSPy-compatible LLM) but optimized for Claude Opus 4.
