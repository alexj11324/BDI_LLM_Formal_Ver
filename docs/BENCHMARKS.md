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

1.  **Structural Hard-Pass Rate**: Percentage of plans with no hard structural errors (non-empty + acyclic).
2.  **Structural Warning Rate**: Percentage of plans with non-blocking structural warnings (for example, disconnected subgraphs).
3.  **Multi-Layer Success**: Percentage of plans that pass structural + symbolic/physics validation.
4.  **Auto-Repair Efficiency**: Rate at which repair converts problematic plans (hard-fail or warning-heavy cases) into executable outputs.

## Results

### Blocksworld (Batch 1, 2026-02-16)

| Run | Instances | Overall Success | Structural | Symbolic | Physics | Auto-Repair |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Batch 1 | 400 | **99.75%** (399/400) | 100% | 99.75% | 99.75% | 100% (1/1) |

> **Note**: Logistics and Depots domains are pending re-evaluation with the new parallel execution pipeline. Previous snapshots showed >99% accuracy.

### Failure Analysis

#### Parallel Tasks
One common failure mode for LLMs is generating "disconnected islands" for tasks that can be performed in parallel.
*   **Issue**: LLM generates two separate action chains for independent goals.
*   **Current behavior**: Layer 1 reports this as a **warning** (not a hard failure), then downstream validation/repair decides whether to connect components.
*   **Repair strategy**: The **Auto-Repair System** can insert virtual `START`/`END` nodes to unify the graph when connected execution is required.

#### Physical Constraints
LLMs occasionally hallucinate valid moves that violate state preconditions (e.g., trying to pick up a block that is underneath another).
*   **Detection**: Caught by Layer 3 (Physics Validator).
*   **Mitigation**: Requires iterative prompting or finer-grained state descriptions.

## Evaluation Commands

To run the benchmarks locally:

```bash
# Run a subset of PlanBench (requires provider credentials)
python scripts/run_planbench_full.py --domain blocksworld --max_instances 10

# Run evaluation unit tests (offline)
python scripts/run_evaluation.py --mode unit

# API-dependent integration tests (auto-skip when credentials unavailable)
pytest tests/test_integration.py -q
```
