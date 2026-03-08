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
- **MCP Server Interoperability**: Fully exposes the verification loop as a Model Context Protocol (MCP) server, allowing Claude Code, Cursor, and other AI Agents to use it as a "Trojan Horse" planning gatekeeper.
- **R1 Distillation Output**: Logs every successful verification trajectory in a rigorous `<think>` format, creating highly valuable structured reasoning datasets for fine-tuning smaller models.

---

## Tech Stack

- **Language**: Python 3.10+
- **Prompting Framework**: DSPy
- **Validation**: Pydantic V2
- **Formal Verification**: Z3 Solver, `VAL` (PDDL Validator)
- **Agent Integration**: Model Context Protocol (MCP) Python SDK
- **Testing**: Pytest
- **Containerization**: Docker

---

## Prerequisites

To run this framework locally, you must have:
- **Python 3.10+** (Python 3.11 recommended)
- **Git**
- **Docker** (Optional, but highly recommended for the MCP server)
- A valid API key from OpenAI, Anthropic, or Google/Vertex.

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
pip install -r requirements.txt
```

### 3. Environment Setup

Copy the example environment variables file to configure your language model API access:

```bash
cp .env.example .env
```

Configure the following standard LLM variables inside `.env`:

| Variable | Description | Example |
| -------- | ----------- | ------- |
| `OPENAI_API_KEY` | OpenAI or any compatible API provider | `sk-xxxx...` |
| `ANTHROPIC_API_KEY` | Anthropic API Key | `sk-ant-xxxx...` |
| `GOOGLE_API_KEY` | Google Gemini API Key | `AIza...` |
| `LLM_MODEL` | Specific model string for DSPy to use | `gpt-5`, `gemini-2.0-flash` |
| `OPENAI_API_BASE` | Custom deployment or CMU gateway | `https://ai-gateway...` |

*(See the Environment Variables section below for full documentation).*

### 4. Ensure VAL Binary is Executable (Local Run)

If you are running the `VAL` verifier locally on macOS (ARM64), ensure it has executable permissions:
```bash
chmod +x planbench_data/planner_tools/VAL/validate
```
*(If you are on Linux or Windows, we recommend using the Docker build, which automatically compiles VAL).*

---

## Architecture Overview

### Directory Structure

```text
BDI_LLM_Formal_Ver/
├── src/
│   ├── bdi_llm/             # Core planning, verification, and repair modules
│   └── interfaces/          # MCP server and CLI entry points
├── scripts/                 # Categorized evaluation/batch/replanning/paper scripts
│   ├── evaluation/          # PlanBench evaluation scripts
│   ├── batch/               # Batch inference scripts
│   ├── replanning/          # Dynamic replanning scripts
│   └── paper/               # Paper figure generation scripts
├── tests/                   # Categorized test suite
│   ├── unit/                # Unit tests
│   ├── integration/         # Integration tests
│   └── smoke/               # Smoke tests
├── docs/                    # All documentation (C4, Conductor, archives)
├── configs/                 # Configuration files and code style guides
└── planbench_data/          # PDDL datasets (Blocksworld, Logistics, etc.)
```

### The PNSV Verification Loop

1. **Intention Generation**: An initial natural language prompt generates a JSON Intention DAG via DSPy.
2. **Pydantic Validation**: Automatically casts JSON into a strictly-typed `IntentionDAG` object.
3. **Core Engine Dispatch**: The `BDIEngine` delegates the DAG to the `VerificationBus`.
4. **Multi-layer Check**: The Verification Bus passes the graph to specialized plugins (like `PlanBenchVerifier` or `SWEVerifier`). These plugins execute structural checks, PDDL VAL validation, and custom domain simulator logic in parallel.
5. **Auto-Repair / Distillation**: 
   - If **failed**: Tracebacks are caught, structured, and passed back into the DSPy engine for auto-correction (up to three loops via the `EpistemicDeadlockError` guard).
   - If **passed**: The successful trajectory is piped into the generic `R1 Distillation Formatter` and flushed into `.jsonl` trace outputs.

---

## Environment Variables

### Required API Configurations

You must provide *at least one* LLM provider key to use the DSPy planner.

| Variable | Description |
| -------- | ----------- |
| `OPENAI_API_KEY` | Connects DSPy to OpenAI or OpenAI-compatible APIs (vLLM, Nim) |
| `ANTHROPIC_API_KEY` | Connects to Claude 3.5/3.7 Family |
| `GOOGLE_API_KEY`| Connects direct Gemini access |
| `GOOGLE_APPLICATION_CREDENTIALS` | Absolute path to Vertex AI JSON credential file |

### Optional Execution Variables

| Variable | Description | Default |
| -------- | ----------- | ------- |
| `LLM_MODEL` | Explicitly overrides the LLM endpoint class | `gpt-4o-mini` |
| `OPENAI_API_BASE` | Alternative target for OpenAI SDK endpoints | - |
| `SAVE_REASONING_TRACE` | Writes CoT tokens to disk per run | `true` |
| `REASONING_TRACE_MAX_CHARS` | Truncates trace logging | `8000` |

---


## Latest Benchmark Snapshot

Latest mainline snapshot on `planner-main` using `run_planbench_full.py`, CPA OpenAI-compatible proxy (`gpt-5(low)`), and `workers=500`.

**Stage semantics**
- `baseline`: strict direct action-generation baseline (not the old shared-BDI `NAIVE` ablation)
- `bdi`: initial BDI checkpoint without repair
- `bdi-repair`: full verify-repair pipeline

| Domain | `baseline` | `bdi` | `bdi-repair` |
| --- | --- | --- | --- |
| `blocksworld` | `1103/1103 (100.0%)` | `1103/1103 (100.0%)` | `1103/1103 (100.0%)` |
| `logistics` | `0/572 (0.0%)` | `557/572 (97.4%)` | `572/572 (100.0%)` |
| `depots` | `498/501 (99.4%)` | `478/501 (95.4%)` | `501/501 (100.0%)` |
| `obfuscated_deceptive_logistics` | `546/572 (95.5%)` | `546/572 (95.5%)` | `572/572 (100.0%)` |
| `obfuscated_randomized_logistics` | `547/572 (95.6%)` | `536/572 (93.7%)` | `572/572 (100.0%)` |

**Key takeaway**: the strict direct `baseline` can fail badly on logistics, while the BDI scaffold recovers most of the domain and the verify-repair loop closes the remaining hard cases to 100%.

---

## Available Scripts

| Command | Description |
| ------- | ----------- |
| `python scripts/evaluation/run_planbench_full.py --domain blocksworld` | Execute the full 100+ blocksworld domain benchmarks |
| `python scripts/evaluation/run_evaluation.py --mode demo` | Run a live CLI demo where you input a prompt and watch the engine verify it |
| `python scripts/evaluation/run_verification_only.py` | Run pure ground-truth validation offline (no LLMs pinged) |
| `python src/interfaces/mcp_server.py` | Launch the server as a Model Context Protocol endpoint |

*Pass `--execution_mode bdi-repair` to run the full baseline → BDI → repair pipeline, `--execution_mode bdi` to stop after the initial BDI checkpoint, or `--execution_mode baseline` for the direct action-generation baseline.*

---

## Testing

The framework relies on Pytest to validate generic modules and isolation logic. Currently it has over 90 active automated checks.

### Running Offline Unit Tests

```bash
# Verify the formal pipeline and generic structure 
pytest tests/
```

### Running API-Dependent Integration Tests

```bash
# Ensures end-to-end BDI generation works. Requires valid API keys.
pytest tests/test_integration.py -q
```
*(Test cases lacking proper `.env` secrets will gracefully `skip` without failing the pipeline).*

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
**Fix**: On Mac, run `chmod +x planbench_data/planner_tools/VAL/validate`. On Linux or Windows WSL, you must compile `VAL` from source by executing `make validate` inside the `planner_tools/VAL` directory, OR simply use the Docker container where compilation is guaranteed. 

### Issue: "Graph Validation Warning: Components disconnected"
**Context**: This is considered a *soft warning* generated by Layer 1 (Structural Validator) when multiple parallel tasks are requested, forming distinct Directed Acyclic Graph structures without paths intersecting. 
**Fix**: None required. Layer 2/3 and the Execution Engine accept partitioned DAGs natively; do not force LLMs to artificially attach parallel actions.

### Issue: "Missing initial state context"
**Error**: Python exception when passing raw PDDL graphs.
**Fix**: Always verify you passed the parsed `init_state` object mapping via `parse_pddl_problem()`, as physics verification requires explicit awareness of truth environments beyond generic natural text representations. 

---

## Further Documentation

- [**Conductor Setup**](docs/conductor/index.md): Design guidelines, Git strategies, and project intent. *(moved from `conductor/`)*
- [**C4 Architecture**](docs/c4/c4-context.md): Deep-dive into Context & Container boundaries.
- [**Technical Reference**](docs/TECHNICAL_REFERENCE.md): 10-chapter technical development manual.
- [**Benchmarking Status**](docs/BENCHMARKS.md): Historical execution outcomes against PlanBench.
- [**Wiki Catalogue**](docs/wiki-catalogue.md): Full top-level repository index.
