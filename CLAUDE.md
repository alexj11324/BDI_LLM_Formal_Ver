# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Runtime scope

The active runtime is the `src/bdi_llm/` package, the entrypoints in `src/interfaces/`, and the current runners in `scripts/evaluation/` and `scripts/replanning/`.

Do **not** treat these as the mainline runtime unless a task explicitly says so:
- `scripts/evaluation/_legacy/` — historical runners kept for reference
- `scripts/swe_bench/` — SWE-bench subsystem (see "Next steps" below; not current focus)
- `workspaces/pnsv_workspace/` — architecture/reference workspace, not the default import path used by current runners

## Setup and common commands

### Install

Use the package metadata in `pyproject.toml` for development installs:

```bash
pip install -e ".[dev]"
cp .env.example .env
```

`requirements.txt` is only a minimal subset and is not the best source for a full local dev environment.

### Lint

```bash
ruff check .
```

### Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit -q

# Single test file
pytest tests/unit/test_travelplanner_review.py -q

# Single test
pytest tests/unit/test_travelplanner_review.py::test_apply_patch_preserves_untouched_days -q

# Offline VAL / symbolic integration
pytest tests/integration/test_val_integration.py -q

# API-backed planner integration
pytest tests/integration/test_integration.py -q
```

Notes:
- Most unit tests are offline.
- `tests/integration/test_integration.py` exercises live planner generation and needs API credentials.
- Local symbolic verification needs a working VAL binary at `workspaces/planbench_data/planner_tools/VAL/validate`.

### Demo and MCP entrypoints

Run these after an editable install so `bdi_llm` imports resolve correctly:

```bash
python src/interfaces/cli.py
python src/interfaces/mcp_server.py
```

### Generic PDDL / PlanBench-style evaluation

```bash
# Single generic PDDL problem
python scripts/evaluation/run_generic_pddl_eval.py --domain_pddl tests/fixtures/gripper/domain.pddl --problem_pddl tests/fixtures/gripper/problem1.pddl

# Batch generic PDDL directory with VAL checking
python scripts/evaluation/run_generic_pddl_eval.py --domain_pddl tests/fixtures/gripper/domain.pddl --problem_dir tests/fixtures/gripper --execution_mode VERIFY_WITH_VAL

# Verification-only evaluation (generation + structural + VAL, no repair)
python scripts/evaluation/run_verification_only.py --domain blocksworld --max_instances 10
```

Use `run_generic_pddl_eval.py` as the current generic PDDL runner. Do not default to `_legacy/run_planbench_full.py` unless the task is explicitly about the old pipeline.

### TravelPlanner

```bash
python scripts/evaluation/run_travelplanner_baseline.py --split validation --max_instances 3 --travelplanner_home workspaces/TravelPlanner_official
python scripts/evaluation/run_travelplanner_bdi.py --split validation --max_instances 3 --travelplanner_home workspaces/TravelPlanner_official
python scripts/evaluation/run_travelplanner_repair.py --split validation --max_instances 3 --travelplanner_home workspaces/TravelPlanner_official

# Release matrix / validation orchestration
python scripts/evaluation/run_travelplanner_release_matrix.py --run-validation --workers 20 --travelplanner-home workspaces/TravelPlanner_official

# Generate test-set submissions
python scripts/evaluation/run_travelplanner_test_submit.py --mode bdi-repair --output_dir runs/tp_test_submit --workers 100
```

TravelPlanner requires:
- the official checkout at `workspaces/TravelPlanner_official/` (or `TRAVELPLANNER_HOME` / `--travelplanner_home`)
- the official database files under that checkout
- access to the Hugging Face `osunlp/TravelPlanner` dataset

## Configuration and runtime assumptions

Configuration lives in `src/bdi_llm/config.py` and is loaded from the environment plus `.env`.

Important variables:
- `OPENAI_API_KEY`
- `OPENAI_API_BASE`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `LLM_MODEL`
- `VAL_VALIDATOR_PATH`
- `SAVE_REASONING_TRACE`
- `REASONING_TRACE_MAX_CHARS`

Important detail: `Config._resolve_key()` ignores placeholder strings like `${VAR}`. Put real values in `.env` or export them in the shell.

The current runtime resolves VAL under:
- `workspaces/planbench_data/planner_tools/VAL/validate`

If local symbolic verification fails on macOS, check executable permissions:

```bash
chmod +x workspaces/planbench_data/planner_tools/VAL/validate
```

## High-level architecture

### 1. Benchmark inputs are normalized into `PlanningTask`

`src/bdi_llm/planning_task.py` defines the benchmark-agnostic planner contract:
- `PlanningTask` — normalized `beliefs`, `desire`, and optional `domain_context`
- `TaskAdapter` — converts benchmark-native inputs into `PlanningTask`
- `PlanSerializer` — converts planner outputs back into benchmark-native format

For generic PDDL, `PDDLTaskAdapter` turns problem files into natural-language beliefs/goals, and `PDDLPlanSerializer` converts a `BDIPlan` back into grounded PDDL actions.

### 2. `BDIPlan` is the core planning data structure

`src/bdi_llm/schemas.py` defines:
- `ActionNode`
- `DependencyEdge`
- `BDIPlan`

`BDIPlan` is a DAG-shaped intermediate plan representation that can be converted to `networkx` for verification.

### 3. `DomainSpec` separates built-in domains from generic PDDL

`src/bdi_llm/planner/domain_spec.py` is the domain abstraction layer.

It provides:
- built-in specs for `blocksworld`, `logistics`, and `depots`
- `DomainSpec.from_pddl()` for arbitrary PDDL domains
- parsed action schemas, required parameters, and prompt-facing `domain_context`
- optional few-shot demonstrations for some domains

This is the reason the planner can serve both fixed benchmark domains and arbitrary PDDL domains without hardcoding everything in the planner constructor.

### 4. `BDIPlanner` is the main DSPy planning module

`src/bdi_llm/planner/bdi_engine.py` is the main planning entrypoint.

Key behaviors:
- `generate_plan()` does plan generation only
- `forward()` adds structural verification on top of generation
- `_validate_action_constraints()` checks action names and required params against the active `DomainSpec`
- `repair_from_val_errors()` performs verifier-guided repair with cache/budget controls

Supporting modules:
- `src/bdi_llm/api_budget.py` — rate limits / repair budget policy
- `src/bdi_llm/repair_cache.py` — avoids repeating identical repair work
- `src/bdi_llm/plan_repair.py` — graph-shape repair such as cycle breaking or reconnecting disconnected components

### 5. Verification is layered

There are two distinct verification layers and they should not be conflated:

- `src/bdi_llm/verifier.py` — **structural** verification only
  - empty graph = hard failure
  - cycle = hard failure
  - disconnected components = warning, not a blocker

- `src/bdi_llm/symbolic_verifier.py` — **symbolic / domain** verification
  - `PDDLSymbolicVerifier` wraps VAL
  - `IntegratedVerifier` orchestrates symbolic + optional domain-specific checks
  - `BlocksworldPhysicsValidator` adds Python-side simulation checks beyond raw VAL output

When debugging failures, first determine whether the issue is:
- graph structure
- PDDL executability / VAL
- domain-specific semantics

### 6. MCP server is a thin interface over the planner/verifier stack

`src/interfaces/mcp_server.py` exposes three FastMCP tools:
- `generate_plan`
- `verify_plan`
- `execute_verified_plan`

`execute_verified_plan` is the gated-execution path: it only runs the requested shell command after the supplied PDDL plan passes verification.

### 7. TravelPlanner is a separate non-PDDL pipeline

TravelPlanner does **not** use `BDIPlan`. Its active runtime is under `src/bdi_llm/travelplanner/`.

The flow is:
1. `travelplanner/adapter.py` converts the official sample into a `PlanningTask`
2. the adapter injects the output contract from `travelplanner/spec.md` into `domain_context`
3. `travelplanner/engine.py` generates a `TravelPlannerItinerary`
4. `travelplanner/serializer.py` converts it into official submission rows
5. `travelplanner/official.py` evaluates it with the official evaluator from `workspaces/TravelPlanner_official`
6. `travelplanner/runner.py` handles checkpointing, summaries, and optional MLflow logging

Repair is split into two layers:
- **non-oracle repair** uses deterministic local critique / patch guardrails from `travelplanner/review.py`
- **oracle repair** uses evaluator feedback during `bdi-repair` evaluation mode

`TRAVELPLANNER_BDI_PROMPT_VERSION` selects the BDI prompt stack in `travelplanner/engine.py`.
Current code defaults to `v3`; `v4` remains available as an experimental path.

### 8. SWE-bench (next step — not current focus)

SWE-bench code lives under `src/bdi_llm/swe_bench/` and `scripts/swe_bench/`. A full 500-instance SWE-bench Verified run scored **34/500 (6.8%)** with GPT-5(low) on 2026-03-11. Results concentrated in small repos (pytest 47%, pylint 50%, astropy 36%) while large repos (django 0/231, sympy 0/75) failed entirely due to search_block matching and environment setup issues. See `runs/swe_bench_full_verified/` on the GCP instance `swe-bench-runner` for detailed results. Further SWE-bench optimization is deferred to future work.

### 9. Other active subsystems

- `scripts/replanning/run_dynamic_replanning.py` + `src/bdi_llm/dynamic_replanner/` — execution-aware replanning after grounded-action failure

## Data and artifact conventions

- `workspaces/planbench_data/` — current PDDL benchmark assets and VAL binary
- `workspaces/TravelPlanner_official/` — external official TravelPlanner checkout used for evaluation
- `runs/` — mutable checkpoints and scratch outputs
- `artifacts/paper_eval_20260213/` — frozen paper evidence snapshot; do not edit or treat mutable reruns as replacements for paper numbers

## Project automation and docs (non-runtime)

- `.ralphy/` + `scripts/ralph/` — Ralph autonomous agent executor (PRD-driven task decomposition with quality gates)
- `paper_icml2026/` — ICML paper artifacts (figures, sections, compiled paper)
- `docs/conductor/` — documentation hub (product, workflow, tech stack, tracks)
- `docs/c4/` — C4 architecture diagrams (context, container, component)

## Known repo gotcha

The current runtime code resolves PlanBench assets under `workspaces/planbench_data/`, while `Dockerfile` still copies a root-level `planbench_data/` tree. Re-check Dockerfile assumptions before relying on container builds for the current mainline runtime.
