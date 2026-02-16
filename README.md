# BDI-LLM Formal Verification Framework

English | [简体中文](README_CN.md)

A framework for generating and verifying BDI plans using LLMs with formal verification guarantees.

## Overview

This project implements a hybrid planning architecture that combines the generative capabilities of LLMs with rigorous formal verification methods. It addresses the hallucination and logical inconsistency problems in LLM-generated plans by enforcing structural and semantic constraints.

### Key Features

*   **Hybrid BDI + LLM Planning**: Generates structured BDI plans (Beliefs, Desires, Intentions) from natural language goals.
*   **Multi-Layer Verification**:
    1.  **Structural Verification**: Ensures the plan forms a valid Directed Acyclic Graph (DAG) and is weakly connected.
    2.  **Symbolic Verification**: Integrates PDDL-based verification (using VAL) to check logical consistency.
    3.  **Physics Validation**: Domain-specific physics validators (e.g., for Blocksworld) to ensure action feasibility.
*   **Auto-Repair Mechanism**: Automatically fixes common structural errors (like disconnected subgraphs) without re-querying the LLM.
*   **Coding Domain Support**: Specialized BDI planner for software engineering tasks (SWE-bench), capable of reading, editing, and testing code.
*   **Benchmarking**: Built-in support for evaluating against the PlanBench dataset.

## PlanBench Results

Evaluated using `vertex_ai/gemini-3-flash-preview` across three planning domains (frozen snapshot: 2026-02-16).

| Domain | Passed | Total | Accuracy |
|---|---|---|---|
| Blocksworld | 399 | 400 | **99.8%** |
| Logistics | 568 | 570 | **99.6%** |
| Depots | 497 | 500 | **99.4%** |
| **Overall** | **1464** | **1470** | **99.6%** |

Only 6 instances failed across all domains (1 new failure in Blocksworld Batch 1). Detailed provenance and SHA256 checksums are available in [Paper Result Provenance](docs/PAPER_RESULT_PROVENANCE.md).

## Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/alexj11324/BDI_LLM_Formal_Ver.git
    cd BDI_LLM_Formal_Ver
    ```

2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

3. Set up environment variables:
    ```bash
    cp .env.example .env
    # Edit .env to add your API_KEY and optionally API_BASE
    nano .env
    ```
    Alternatively, export them directly:
    ```bash
    export OPENAI_API_KEY="your-api-key"
    # Optional: Set a custom API base URL if using a gateway
    export OPENAI_API_BASE="https://your-gateway-url/v1"
    ```

## Usage

### Running Evaluations

Run the main evaluation script to test the framework:

```bash
python scripts/run_evaluation.py --mode [unit|demo|benchmark]
```

*   `unit`: Run unit tests for core components.
*   `demo`: Run a live LLM demo with auto-repair.
*   `benchmark`: Run evaluations on the PlanBench dataset.

### Project Structure

```
BDI_LLM_Formal_Ver/
├── src/bdi_llm/                          # Core planner + verification modules
├── scripts/                              # Evaluation and utility scripts
├── tests/                                # Unit and integration tests
├── docs/                                 # User/system/provenance docs
├── planbench_data/                       # PlanBench data + VAL binaries
├── runs/                                 # Mutable outputs + legacy runs (see runs/README.md)
│   └── legacy/planbench_results_20260211/  # Historical pre-freeze outputs
├── artifacts/paper_eval_20260213/        # Frozen paper evidence snapshot
├── planbench_results_archive.tar.gz      # Raw archived experiment bundle
└── requirements.txt                      # Project dependencies
```

## Documentation

*   [User Guide](docs/USER_GUIDE.md): Detailed guide on usage and configuration.
*   [Architecture](docs/ARCHITECTURE.md): System architecture and verification layers.
*   [Benchmarks](docs/BENCHMARKS.md): Evaluation methodology and results.
*   [Paper Result Provenance](docs/PAPER_RESULT_PROVENANCE.md): Frozen paper-result evidence chain and verification procedure.
*   [Repo Organization](docs/REPO_ORGANIZATION.md): Directory responsibilities and cleanup rules.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Current Status & Next Steps (Updated 2026-02-16)

**Recent Accomplishments:**
- Implemented Coding Domain (Phase 4): `CodingBDIPlanner`, PDDL domain, local SWE-bench harness.
- Optimized PlanBench (Phase 5): Batch 1 (400 instances) completed with 99.8% success (399/400).

**Priority Queue for Next Session:**
1.  **Analyze PlanBench Failure**: Investigate the single failure case in Batch 1 (`runs/planbench_results/results_blocksworld_20260216_162051.json`).
2.  **Expand SWE-bench**: Run `scripts/run_iterative_fix.py` on more instances (e.g., top 5 verified) to robustify the agent.
3.  **Continue PlanBench Batches**: Execute Batch 2 (400-800) and Batch 3 (800-1103) to complete the benchmark.
