# BDI-LLM Formal Verification Framework (PNSV)

English | [简体中文](README_CN.md)

A neuro-symbolic planning framework combining Large Language Models (LLMs) with formal verification to produce provably correct, hallucination-free action plans.

## Key Features

- **Hybrid BDI + LLM Planning**: Generates structured Belief-Desire-Intention (BDI) plans as Directed Acyclic Graphs (DAGs) from natural language goals using DSPy Chain-of-Thought reasoning.
- **3-Layer Verification Pipeline**:
  1. **Structural Verification**: Hard checks for DAG compliance (empty graphs, cycles) + soft warnings for disconnected components.
  2. **Symbolic Verification**: PDDL precondition/effect evaluation via the classic `VAL` planning binary.
  3. **Physics/Domain Simulation**: Custom Python-based formal verification for specific domains (e.g., Blocksworld stacking logic, SWE-bench environment checks).
- **Auto-Repair Engine**: Intercepts verification tracebacks and self-corrects invalid graphs (handling cycles, topological fixes, and PDDL parameter corrections) automatically without prompt leakage.
- **Few-Shot Learning**: Domain-specific YAML demonstration files for both plan generation and repair, improving LLM output quality.
- **Dynamic Replanning**: Runtime re-planning when simulated execution diverges from expected world state, with BeliefBase tracking and recovery plan generation.
- **MCP Server Interoperability**: Fully exposes the verification loop as a Model Context Protocol (MCP) server, allowing Claude Code, Cursor, and other AI Agents to use it as a "Trojan Horse" planning gatekeeper.
- **Batch Inference**: DashScope Batch API integration for large-scale PlanBench evaluations.
- **R1 Distillation Output**: Logs every successful verification trajectory in a rigorous `<think>` format, creating structured reasoning datasets for fine-tuning smaller models.

---

## Tech Stack

- **Language**: Python 3.10+
- **Prompting Framework**: DSPy (≥2.4)
- **Validation**: Pydantic V2
- **Formal Verification**: Z3 Solver, `VAL` (PDDL Validator)
- **Graph Analysis**: NetworkX (≥3.0)
- **LLM Providers**: DashScope (primary), OpenAI, Anthropic, Google/Vertex AI
- **Agent Integration**: Model Context Protocol (MCP) Python SDK
- **Testing**: Pytest
- **Containerization**: Docker

---

## Prerequisites

To run this framework locally, you must have:
- **Python 3.10+** (Python 3.11 recommended)
- **Git**
- **Docker** (Optional, but recommended for the MCP server)
- A valid API key from DashScope (primary), OpenAI, Anthropic, or Google/Vertex.

---

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/alexj11324/BDI_LLM_Formal_Ver.git
cd BDI_LLM_Formal_Ver
```

### 2. Install Dependencies

It is highly recommended to use a virtual environment (`venv`, `conda`, `uv`, etc.):

```bash
pip install -e .

# Or with development dependencies:
pip install -e ".[dev]"
pre-commit install
```

### 3. Environment Setup

Copy the example environment variables file to configure your language model API access:

```bash
cp .env.example .env

# Optional test-only local overrides:
cp .env.test.example .env.test
```

`.env`, `.env.test`, and other `.env.*` local override files are gitignored on purpose.
Only example templates should be committed. The repository now blocks committed
secrets both locally through `pre-commit` and in CI through the `Secret Scan`
workflow.

Configure the following standard LLM variables inside `.env`:

| Variable | Description | Example |
| -------- | ----------- | ------- |
| `DASHSCOPE_API_KEY` | DashScope API key (primary provider) | `sk-xxxx...` |
| `OPENAI_API_KEY` | OpenAI or any compatible API provider | `sk-xxxx...` |
| `ANTHROPIC_API_KEY` | Anthropic API Key | `sk-ant-xxxx...` |
| `GOOGLE_API_KEY` | Google Gemini API Key | `AIza...` |
| `LLM_MODEL` | Specific model string for DSPy to use | `openai/gpt-4o`, `qwq-plus` |
| `OPENAI_API_BASE` | Custom deployment or gateway | `https://dashscope.aliyuncs.com/...` |

*(See the [Environment Variables](#environment-variables) section below for full documentation).*

### 4. Ensure VAL Binary is Executable (Local Run)

If you are running the `VAL` verifier locally on macOS (ARM64), ensure it has executable permissions:
```bash
chmod +x workspaces/planbench_data/planner_tools/VAL/validate
```
*(If you are on Linux or Windows, we recommend using the Docker build, which automatically compiles VAL).*

> **Note**: The VAL path is auto-detected via `Config._default_val_path`. You can override it with the `VAL_VALIDATOR_PATH` environment variable.

---

## Architecture Overview

### The PNSV Verification Loop

```
NL Goal → DSPy Planner → BDIPlan (DAG)
       → 3-Layer Verification:
         1. Structural (DAG checks)
         2. Symbolic (PDDL/VAL)
         3. Physics (domain simulation)
       → Pass? → ✅ Verified Plan → R1 Distillation
       → Fail? → Auto-Repair (up to 3 iterations)
              → Re-verify
```

### Directory Structure

```text
BDI_LLM_Formal_Ver/
├── src/
│   ├── bdi_llm/             # Core planning, verification, and repair modules
│   │   ├── planner/          # BDI engine + DSPy signatures + few-shot demos
│   │   ├── dynamic_replanner/# Runtime replanning on execution failure
│   │   ├── data/             # Few-shot YAML demonstration files
│   │   ├── schemas.py        # BDIPlan, ActionNode, DependencyEdge
│   │   ├── verifier.py       # Layer 1: Structural verification
│   │   ├── symbolic_verifier.py  # Layer 2+3: Symbolic + Physics
│   │   ├── plan_repair.py    # Auto-repair + canonicalization
│   │   └── ...               # Budget, batch, config, visualizer
│   └── interfaces/           # MCP server and CLI entry points
├── scripts/                  # Evaluation, batch, replanning, paper scripts
├── tests/                    # Unit, integration, smoke tests
├── docs/                     # Full documentation suite
│   ├── c4/                   # C4 architecture diagrams
│   ├── conductor/            # Project configuration & guidelines
│   ├── wiki-catalogue.md     # Wiki document structure
│   └── TECHNICAL_REFERENCE.md # 10-chapter technical manual
└── workspaces/               # PDDL datasets and VAL tool
```

---

## Environment Variables

### Required API Configurations

You must provide *at least one* LLM provider key to use the DSPy planner.

| Variable | Description |
| -------- | ----------- |
| `DASHSCOPE_API_KEY` | Primary provider — DashScope (qwq-plus) via OpenAI-compatible API |
| `OPENAI_API_KEY` | Connects DSPy to OpenAI or OpenAI-compatible APIs. Falls back to `DASHSCOPE_API_KEY` |
| `ANTHROPIC_API_KEY` | Connects to Claude 3.5/3.7 Family |
| `GOOGLE_API_KEY`| Connects direct Gemini access |
| `GOOGLE_APPLICATION_CREDENTIALS` | Absolute path to Vertex AI JSON credential file |

### Optional Execution Variables

| Variable | Description | Default |
| -------- | ----------- | ------- |
| `LLM_MODEL` | Explicitly overrides the LLM model | `openai/gpt-5` |
| `OPENAI_API_BASE` | Alternative target for OpenAI SDK endpoints | — |
| `VAL_VALIDATOR_PATH` | Path to VAL binary (auto-detected if unset) | — |
| `LLM_MAX_TOKENS` | Max generation tokens | `4000` |
| `LLM_TEMPERATURE` | Generation temperature | `0.2` |
| `REASONING_EFFORT` | Reasoning depth control | `medium` |
| `SAVE_REASONING_TRACE` | Writes CoT tokens to disk per run | `false` |
| `REASONING_TRACE_MAX_CHARS` | Truncates trace logging | `8000` |
| `API_BUDGET_MAX_CALLS_PER_INSTANCE` | Max API calls per problem instance | `5` |
| `API_BUDGET_MAX_RPM` | Requests per minute limit | `60` |

---

## Available Scripts

| Command | Description |
| ------- | ----------- |
| `python scripts/evaluation/run_planbench_full.py --domain blocksworld` | Execute the full 100+ blocksworld domain benchmarks |
| `python scripts/evaluation/run_planbench_full.py --all_domains --execution_mode BDI_REPAIR` | Full evaluation across all domains with 3-layer verification + repair |
| `python scripts/evaluation/run_verification_only.py` | Run pure ground-truth validation offline (no LLMs pinged) |
| `python scripts/replanning/run_dynamic_replanning.py --domain blocksworld` | Dynamic replanning with execution simulation |
| `python scripts/batch/submit_batch.py --input batch.jsonl` | Submit batch inference to DashScope |
| `python src/interfaces/mcp_server.py` | Launch the MCP server |
| `python src/interfaces/cli.py` | Run a quick CLI demo |

### Execution Modes

| Mode | Flag | Description |
|------|------|-------------|
| BASELINE | `--execution_mode BASELINE` | Raw LLM output, no verification |
| BDI | `--execution_mode BDI` | Structured BDI generation, no verification |
| BDI_REPAIR | `--execution_mode BDI_REPAIR` | 3-layer verification + auto-repair loop |

---

## Testing

The framework relies on Pytest to validate generic modules and isolation logic.

### Running Offline Unit Tests

```bash
# Verify the formal pipeline and generic structure 
pytest tests/
```

### Running API-Dependent Integration Tests

```bash
# Ensures end-to-end BDI generation works. Requires valid API keys.
pytest tests/integration/ -q
```
*(Test cases lacking proper `.env` secrets will gracefully `skip` without failing the pipeline).*

---

## Current Benchmark Snapshot

Latest full PlanBench snapshot using the CPA endpoint with `gpt-5(low)` and
`workers=1000`.

Metric definitions used below:

- `baseline`: direct action generation baseline (`BASELINE`), judged by `VAL`
- `bdi`: initial BDI generation success before any repair, judged by the same verifier stack
- `bdi_repair`: final `BDI_REPAIR` success after the repair loop

| Domain | Total | `baseline` | `bdi` | `bdi_repair` |
| ------ | -----:| ----------:| -----:| ------------:|
| `blocksworld` | 1103 | `1103/1103 (100.0%)` | `1099/1103 (99.6%)` | `1100/1103 (99.7%)` |
| `depots` | 501 | `498/501 (99.4%)` | `492/501 (98.2%)` | `500/501 (99.8%)` |
| `logistics` | 572 | `560/572 (97.9%)` | `563/572 (98.4%)` | `571/572 (99.8%)` |
| `obfuscated_deceptive_logistics` | 572 | `558/572 (97.6%)` | `567/572 (99.1%)` | `571/572 (99.8%)` |
| `obfuscated_randomized_logistics` | 572 | `567/572 (99.1%)` | `559/572 (97.7%)` | `569/572 (99.5%)` |
| **Total** | **3320** | **3286/3320 (99.0%)** | **3280/3320 (98.8%)** | **3311/3320 (99.7%)** |

Repair contribution inside `bdi_repair`:

- `blocksworld`: `1` repaired success
- `depots`: `8` repaired successes
- `logistics`: `8` repaired successes
- `obfuscated_deceptive_logistics`: `4` repaired successes
- `obfuscated_randomized_logistics`: `10` repaired successes
- total repaired successes: `31`

Notes:

- The standalone `BDI` execution mode is intentionally not used as a correctness column here, because it skips verifier-driven validation and repair.
- These numbers supersede earlier README-level benchmark statements that were collected before the obfuscated-domain repair fixes and CPA high-concurrency tuning.

---

## Deployment (MCP Server via Docker)

For production tasks, agents should consume the BDI framework as an MCP tool executing within a strictly sandboxed container. The `Dockerfile` natively handles compiling the complex C++ `VAL` binary, bypassing all multi-platform dependency headaches.

### 1. Build the formal image

```bash
docker build -t bdi-verifier .
```

### 2. Run the MCP Pipeline

```bash
docker run -i --rm -e OPENAI_API_KEY=$OPENAI_API_KEY bdi-verifier
```

### Exposing to Claude Desktop

Add this configuration to your local `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "bdi-pnsv-verifier": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "OPENAI_API_KEY=YOUR_API_KEY", "bdi-verifier"]
    }
  }
}
```

The server exposes `generate_verified_plan` ensuring tools invoke commands only if the verification bus permits the formal transition.

---

## Troubleshooting

### Issue: "VAL binary missing or execution denied"
**Error**: `subprocess.CalledProcessError` or "Permission denied" regarding VAL execution.  
**Fix**: On Mac, run `chmod +x workspaces/planbench_data/planner_tools/VAL/validate`. On Linux or Windows WSL, you must compile `VAL` from source by executing `make validate` inside the `planner_tools/VAL` directory, OR simply use the Docker container where compilation is guaranteed. 

### Issue: "Graph Validation Warning: Components disconnected"
**Context**: This is considered a *soft warning* generated by Layer 1 (Structural Validator) when multiple parallel tasks are requested, forming distinct Directed Acyclic Graph structures without paths intersecting.  
**Fix**: None required. Layer 2/3 and the Execution Engine accept partitioned DAGs natively; do not force LLMs to artificially attach parallel actions.

### Issue: "Missing initial state context"
**Error**: Python exception when passing raw PDDL graphs.  
**Fix**: Always verify you passed the parsed `init_state` object mapping via `parse_pddl_problem()`, as physics verification requires explicit awareness of truth environments beyond generic natural text representations. 

---

## Further Documentation

- [**Wiki Catalogue**](docs/wiki-catalogue.md): Full top-level repository index with hierarchical document structure.
- [**C4 Architecture**](docs/c4/c4-context.md): Deep-dive into Context, Container, Component & Code boundaries.
- [**Technical Reference**](docs/TECHNICAL_REFERENCE.md): 10-chapter technical development manual.
- [**Conductor Setup**](docs/conductor/index.md): Design guidelines, Git strategies, and project intent.
- [**Benchmarking Status**](docs/BENCHMARKS.md): Historical execution outcomes against PlanBench.
- [**User Guide**](docs/USER_GUIDE.md): Comprehensive usage documentation.
