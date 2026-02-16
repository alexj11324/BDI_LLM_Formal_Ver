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
*   **Benchmarking**: Built-in support for evaluating against the PlanBench dataset.

## PlanBench Results

Evaluated using `vertex_ai/gemini-3-flash-preview` across three planning domains (frozen snapshot: 2026-02-13).

| Domain | Passed | Total | Accuracy |
|---|---|---|---|
| Blocksworld | 200 | 200 | **100.0%** |
| Logistics | 568 | 570 | **99.6%** |
| Depots | 497 | 500 | **99.4%** |
| **Overall** | **1265** | **1270** | **99.6%** |

Only 5 instances failed across all domains. Detailed provenance and SHA256 checksums are available in [Paper Result Provenance](docs/PAPER_RESULT_PROVENANCE.md).

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

### MCP Server (Model Context Protocol)

The verifier can be run as an MCP Server, allowing AI agents (like Claude Desktop) to use it as a tool.

1.  **Build Docker Image**:
    ```bash
    docker build -t bdi-verifier .
    ```

2.  **Run Server**:
    ```bash
    docker run -i --rm -e OPENAI_API_KEY=$OPENAI_API_KEY bdi-verifier
    ```

The server exposes:
*   `generate_plan`: Generate BDI plans.
*   `verify_plan`: Verify PDDL plans (Structural + Symbolic).
*   `execute_verified_plan`: Execute commands ONLY if verification passes ("Trojan Horse" pattern).

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
