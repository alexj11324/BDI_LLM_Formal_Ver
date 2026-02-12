# Evaluation & Benchmarks

This document outlines the evaluation methodology and results for the BDI-LLM Framework.

## Methodology

We evaluate the framework using the **PlanBench** dataset (Valmeekam et al., 2023), focusing on the **Blocksworld** domain. This domain provides a rigorous testbed for reasoning about physical constraints and prerequisites.

### Test Set
*   **Source**: [PlanBench](https://github.com/karthikv792/gpt-plan-benchmark)
*   **Domain**: Blocksworld (4 operations: pick-up, put-down, stack, unstack)
*   **Instances**: Derived from IPC (International Planning Competition) generated problems.

### Metrics

We track success rates across different validation layers:

1.  **Structural Accuracy**: Percentage of plans that form a valid DAG (no cycles, fully connected).
2.  **Multi-Layer Success**: Percentage of plans that pass **both** structural checks and domain physics validation.
3.  **Auto-Repair Efficiency**: Rate at which structurally invalid plans are successfully repaired by the heuristic system.

## Preliminary Results

### Phase 2 Evaluation (Snapshot)

| Metric | Success Rate | Notes |
| :--- | :--- | :--- |
| **Structural Accuracy** | **93.75%** | High success rate due to prompt engineering & schemas |
| **Multi-Layer Success** | **~60%** | Physics checks catch subtle logical errors (e.g., unstacking order) |
| **Auto-Repair Success** | **100%** | Successfully creates connectivity for parallel tasks |

### Failure Analysis

#### Parallel Tasks
One common failure mode for LLMs is generating "disconnected islands" for tasks that can be performed in parallel.
*   **Issue**: LLM generates two separate action chains for independent goals.
*   **Solution**: The **Auto-Repair System** detects this and inserts virtual `START`/`END` nodes to unify the graph.

#### Physical Constraints
LLMs occasionally hallucinate valid moves that violate state preconditions (e.g., trying to pick up a block that is underneath another).
*   **Detection**: Caught by Layer 3 (Physics Validator).
*   **Mitigation**: Requires iterative prompting or finer-grained state descriptions.

## Evaluation Commands

To run the benchmarks locally:

```bash
# Run a subset of PlanBench (requires API Key)
python scripts/run_planbench_full.py --domain blocksworld --max_instances 10

# Run evaluation unit tests (No API Key)
python scripts/run_evaluation.py --mode unit
```
