# CLAUDE.md

## Project Overview

BDI-LLM Formal Verification Framework — a neuro-symbolic planning system that uses LLMs as "Generative Compilers" to translate natural language goals into formally verified BDI (Belief-Desire-Intention) plan graphs. Plans are subjected to three-layer verification (structural, symbolic via PDDL/VAL, and domain-specific physics) to eliminate hallucinations and logical inconsistencies.

## Repository Structure

```
BDI_LLM_Formal_Ver/
├── src/bdi_llm/              # Core framework source code
│   ├── planner.py            # LLM-based BDI planner (DSPy signatures)
│   ├── verifier.py           # Structural verification (DAG, connectivity)
│   ├── symbolic_verifier.py  # PDDL symbolic verification + BlocksworldPhysicsValidator
│   ├── plan_repair.py        # Auto-repair for invalid plans
│   ├── visualizer.py         # NetworkX graph visualization
│   ├── schemas.py            # Pydantic models (ActionNode, DependencyEdge, BDIPlan)
│   └── config.py             # Configuration (API keys, model selection, VAL path)
├── tests/                    # Unit and integration tests (pytest)
├── scripts/                  # Evaluation, benchmarking, and figure generation scripts
├── docs/                     # Architecture, user guide, benchmarks, provenance docs
├── planbench_data/           # PlanBench dataset + VAL validator binaries (Linux)
├── artifacts/paper_eval_20260213/  # Frozen paper evidence snapshot (DO NOT modify)
├── runs/                     # Mutable experiment outputs (see runs/README.md)
├── requirements.txt          # Python dependencies
├── pytest.ini                # Pytest configuration
└── .env.example              # Environment variable template
```

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env to add API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, or GOOGLE_API_KEY)
```

## Common Commands

### Run tests
```bash
pytest tests/ -v
```

### Run evaluation
```bash
python scripts/run_evaluation.py --mode unit      # Unit tests
python scripts/run_evaluation.py --mode demo      # Live LLM demo
python scripts/run_evaluation.py --mode benchmark  # PlanBench benchmark
```

### Run full PlanBench evaluation
```bash
python scripts/run_planbench_full.py
```

### Verify frozen paper artifacts
```bash
python scripts/verify_paper_eval_snapshot.py
```

## Architecture

### Verification Pipeline

Plans flow through three verification layers in order:

1. **Structural Verification** (`verifier.py`): Checks the plan is a valid DAG — no cycles, weakly connected, topologically sortable. Uses NetworkX.
2. **Symbolic Verification** (`symbolic_verifier.py`): Validates against PDDL domain/problem definitions using the external VAL binary. Parses VAL output with compiled regexes to extract precondition/effect errors.
3. **Physics Validation** (`symbolic_verifier.py` → `BlocksworldPhysicsValidator`): Simulates plan execution to check domain-specific physical constraints (e.g., block stacking rules).

If structural verification fails, the **Auto-Repair** system (`plan_repair.py`) attempts heuristic fixes (connecting disconnected subgraphs, unifying root/terminal nodes) before re-verification.

### Data Models

All plan structures use Pydantic models defined in `schemas.py`:
- `ActionNode`: Atomic action with id, action_type, params, description
- `DependencyEdge`: Directed dependency (source → target)
- `BDIPlan`: Complete plan with nodes, edges, and goal_description. Has `.to_networkx()` for graph conversion.

### LLM Integration

Uses the DSPy framework (`dspy-ai`) for structured prompting. Domain-specific DSPy signatures are defined in `planner.py`:
- `GeneratePlan`: Blocksworld domain signature
- `GeneratePlanLogistics`: Logistics domain signature

Supported LLM providers: OpenAI, Anthropic, Google/Gemini, Vertex AI. Model selection via `LLM_MODEL` env var (default: `openai/gpt-4o`).

### External Tools

- **VAL** (Plan Validation Tool): PDDL validator binary at `planbench_data/planner_tools/VAL/validate`. Linux ELF only; macOS has graceful fallbacks.

## Code Conventions

### Naming
- Classes: `PascalCase` (e.g., `PlanVerifier`, `ActionNode`, `BDIPlan`)
- Functions/methods: `snake_case` (e.g., `verify_plan`, `to_networkx`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `VIRTUAL_START`, `VIRTUAL_END`)
- Test files: `test_*.py`
- Blocksworld action types: lowercase with hyphens (`pick-up`, `put-down`, `stack`, `unstack`)

### Patterns
- Verification results are `Tuple[bool, List[str]]` — `(is_valid, error_messages)`
- Pydantic `BaseModel` for all data schemas; use `model_dump()` not deprecated `dict()`
- Static methods on verifier classes (no instance state needed)
- Compiled regexes for performance in symbolic_verifier.py (`_re_precond_verbose`, etc.)
- Subprocess with try-finally for VAL invocation cleanup
- `ast.literal_eval()` for parsing (never `eval()` — fixed ACE vulnerability)

### Testing
- Unit tests mock external dependencies (LLM APIs, VAL subprocess)
- Integration tests combine multiple verification layers
- All tests in `tests/` directory, discovered by pytest via `pytest.ini`

## Important Constraints

- **Never use `eval()`** — use `ast.literal_eval()` for safe parsing. This was a fixed security vulnerability.
- **`artifacts/paper_eval_20260213/`** is a frozen evidence snapshot for paper results. Never modify files in this directory.
- **`runs/`** is mutable output space. For publication numbers, always reference the frozen `artifacts/` checkpoint files.
- **VAL binary** is Linux-only. Tests that depend on VAL should mock the subprocess or handle platform gracefully.
- **API keys** are loaded from environment or `.env` file. Never commit credentials. The `.env` file is gitignored.

## Supported Domains

| Domain | Physics Validator | PDDL Support |
|---|---|---|
| Blocksworld | `BlocksworldPhysicsValidator` | Yes |
| Logistics | Structural only | Yes |
| Depots | Structural only | Yes |

## Key Documentation

- [Architecture](docs/ARCHITECTURE.md) — System design and verification layers
- [User Guide](docs/USER_GUIDE.md) — Installation, usage, configuration
- [Benchmarks](docs/BENCHMARKS.md) — Evaluation methodology and results
- [Paper Result Provenance](docs/PAPER_RESULT_PROVENANCE.md) — Frozen evidence chain
- [Repo Organization](docs/REPO_ORGANIZATION.md) — Directory responsibilities and mutability policy
