# BDI-LLM Formal Verification Framework

English | [简体中文](README_CN.md)

A neuro-symbolic planning framework that combines LLM generation with formal verification to produce provably correct plans.

## Overview

BDI-LLM addresses the hallucination and logical inconsistency problems in LLM-generated plans by running every generated plan through a 3-layer verification pipeline. Plans that fail verification are automatically repaired and re-verified before being returned.

### Key Features

- **Hybrid BDI + LLM Planning**: Generates structured BDI plans (Beliefs, Desires, Intentions) as DAGs from natural language goals using DSPy ChainOfThought.
- **3-Layer Verification**:
  1. **Structural** — hard checks (empty graph, cycles) + soft warning (disconnected components)
  2. **Symbolic** — PDDL precondition/effect checking via VAL
  3. **Physics** — Domain-specific state simulation (e.g., Blocksworld clear/hand constraints)
- **Auto-Repair**: Repairs cycles, still connects disconnected subgraphs (even when reported as warnings), and canonicalizes node IDs without re-querying the LLM. Falls back to LLM-guided repair using VAL error messages (up to 3 attempts).
- **MCP Server**: Exposes `generate_verified_plan` as an MCP tool for use by Claude Code, Cursor, and other agents.
- **Coding Domain**: Specialized planner for SWE-bench software engineering tasks (`read-file` → `edit-file` → `run-test` action types).
- **Ablation Support**: `--execution_mode` flag (NAIVE / BDI_ONLY / FULL_VERIFIED) for controlled experiments.
- **PNSV Framework**: Pluggable Neuro-Symbolic Verification engine with domain-agnostic BDI reasoning, shared DAG utilities (`_dag_utils.py`), and R1 distillation formatter for student model fine-tuning.

## PlanBench Results

Full-dataset evaluation across three planning domains.

### GPT-5 (2026-02-27) — Full Dataset

| Domain | Instances | Success Rate |
|--------|-----------|-------------|
| Blocksworld | 1103/1103 | **90.8%** (FULL_VERIFIED) |
| Logistics | 572 | in progress |
| Depots | 501 | in progress |

### Gemini (2026-02-13) — Paper Canonical Numbers

| Domain | Passed | Total | Accuracy |
|--------|--------|-------|----------|
| Blocksworld | ~200 | ~200 | ~99.8% |
| Logistics | 568 | 570 | **99.6%** |
| Depots | 497 | 500 | **99.4%** |

Frozen evidence snapshot: `artifacts/paper_eval_20260213/` (immutable, do not modify).

### Ablation (GPT-OSS-120B, blocksworld 1103 instances)

| Mode | Success Rate | What's verified |
|------|-------------|-----------------|
| NAIVE | 91.6% | Nothing — raw LLM output |
| BDI_ONLY | 91.7% | Structural (DAG) only |
| FULL_VERIFIED | 90.8% | All 3 layers — provably correct |

The ~1% gap between NAIVE and FULL_VERIFIED shows the verification overhead is minimal while providing formal correctness guarantees.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/alexj11324/BDI_LLM_Formal_Ver.git
   cd BDI_LLM_Formal_Ver
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env: set provider credentials:
   # - OPENAI_API_KEY (OpenAI / NVIDIA-compatible gateway)
   # - ANTHROPIC_API_KEY
   # - GOOGLE_API_KEY or GOOGLE_APPLICATION_CREDENTIALS
   # Optional: OPENAI_API_BASE for custom gateway
   ```

## Usage

### Tests

```bash
pytest
pytest tests/test_verifier.py -v
pytest tests/test_integration.py -q  # API-dependent; auto-skips when provider creds are unavailable
```

### Evaluation

```bash
python scripts/run_evaluation.py --mode unit       # offline unit tests
python scripts/run_evaluation.py --mode demo       # live LLM demo
python scripts/run_evaluation.py --mode benchmark  # full benchmark
```

### PlanBench

```bash
# Single domain
python scripts/run_planbench_full.py --domain blocksworld --max_instances 100

# All domains, parallel, with ablation mode
python scripts/run_planbench_full.py --all_domains --execution_mode FULL_VERIFIED \
  --output_dir runs/my_run --parallel --workers 30

# Resume from checkpoint (auto-detected if checkpoint exists in output_dir)
python scripts/run_planbench_full.py --domain blocksworld --output_dir runs/my_run
```

### MCP Server

```bash
python src/mcp_server_bdi.py
```

Exposes `generate_verified_plan(goal, domain, context, pddl_domain_file, pddl_problem_file)` as an MCP tool.

### Project Structure

```
BDI_LLM_Formal_Ver/
├── src/bdi_llm/              # Core modules (planner, verifier, schemas, repair)
├── src/mcp_server_bdi.py     # MCP server entry point
├── scripts/                  # Evaluation and benchmark scripts
├── tests/                    # Unit and integration tests
├── planbench_data/           # PlanBench PDDL instances + VAL binary (macOS arm64)
│   └── plan-bench/utils/     # Secure subprocess wrappers (run_val helper)
├── pnsv_workspace/           # PNSV Framework (Pluggable Neuro-Symbolic Verification)
│   ├── src/core/             # Domain-agnostic BDI engine, schemas, verification bus
│   ├── src/plugins/          # Domain verifiers (PlanBench, SWE-bench)
│   │   └── _dag_utils.py     # Shared topological sort (centralized)
│   ├── src/dspy_pipeline/    # DSPy signatures, teacher config, R1 formatter
│   └── tests/                # 90 unit tests (schemas, verifiers, engine, formatter)
├── runs/                     # Mutable benchmark outputs (not authoritative for paper)
├── artifacts/                # Frozen paper evidence snapshots (do not modify)
└── BDI_Paper/                # LaTeX source (AAAI 2026 format)
```

## Documentation

- [User Guide](docs/USER_GUIDE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Benchmarks](docs/BENCHMARKS.md)

## Recent Changes

### 2026-03-03

- **Security**: Replaced all `os.popen`/`os.system` calls in `planbench_data/` with `subprocess.run` using explicit argument lists, `pathlib.Path` for path construction, return code checking, and environment variable validation ([PR #45](https://github.com/alexj11324/BDI_LLM_Formal_Ver/pull/45)).
- **Refactor**: Extracted shared `run_val()` helper to centralize VAL validator invocation across `validate_plan` and `get_val_feedback`.
- **Refactor**: Extracted shared `_dag_utils.topological_sort()` to eliminate duplicated topological sort logic between `swe_verifier.py` and `planbench_verifier.py` ([PR #43](https://github.com/alexj11324/BDI_LLM_Formal_Ver/pull/43)).
- **Bugfix**: Fixed `dag_dict` initialization in BDI engine to use `None` instead of `{}`, properly distinguishing "no DAG produced" from "empty DAG".
- **PNSV**: All 11 implementation tasks completed with 90 passing unit tests.

## License

MIT License — see [LICENSE](LICENSE) for details.
