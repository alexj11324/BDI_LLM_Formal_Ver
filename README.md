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
├── src/
│   └── bdi_llm/            # Core package
│       ├── planner.py      # BDI Planner with LLM integration
│       ├── verifier.py     # Graph & PDDL verification logic
│       ├── plan_repair.py  # Auto-repair mechanisms
│       └── config.py       # Configuration management
├── scripts/
│   ├── run_evaluation.py   # Main entry point for demos/tests
│   └── run_planbench_*.py  # Benchmark runners
├── tests/                  # Unit and integration tests
├── docs/
│   ├── INTEGRATION_GUIDE.md
│   └── research/           # Research proposals & literature reviews
├── planbench_data/         # PlanBench dataset (PDDL files)
└── requirements.txt        # Project dependencies
```

## Documentation

*   [User Guide](docs/USER_GUIDE.md): Detailed guide on usage and configuration.
*   [Architecture](docs/ARCHITECTURE.md): System architecture and verification layers.
*   [Benchmarks](docs/BENCHMARKS.md): Evaluation methodology and results.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
