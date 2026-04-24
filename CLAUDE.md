# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Runtime scope

The active runtime is the `src/bdi_llm/` package, the entrypoints in `src/interfaces/`, and the current runners in `scripts/evaluation/` and `scripts/replanning/`.

Do **not** treat these as the mainline runtime unless a task explicitly says so:
- `scripts/evaluation/_legacy/` — historical runners kept for reference
- `scripts/swe_bench/` — SWE-bench subsystem has been removed/deferred; no active runner here

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

`pyproject.toml` defines only `[tool.ruff.lint]` (line-length 100, mccabe max-complexity 15) — no explicit `[tool.ruff.format]` block. `ruff format` runs with defaults; `ruff format --check .` to verify without rewriting.

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
- Local symbolic verification needs a working VAL binary at `planbench_data/planner_tools/VAL/validate`.
- CI runs `pytest -v tests/` with `PYTHONPATH=src` (see `.github/workflows/ci.yml`); locally that env var is unnecessary because `pip install -e ".[dev]"` exposes `src/` via the editable install.

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

# Built-in PlanBench paper-aligned evaluation
python scripts/evaluation/run_planbench_paperaligned.py --domain blocksworld --execution_mode bdi-repair --max_instances 10
```

Use `run_generic_pddl_eval.py` as the current generic PDDL runner. Do not default to `_legacy/run_planbench_full.py` unless the task is explicitly about the old pipeline.

### TravelPlanner

```bash
python scripts/evaluation/run_travelplanner_baseline.py --split validation --max_instances 3 --travelplanner_home /path/to/TravelPlanner_official
python scripts/evaluation/run_travelplanner_bdi.py --split validation --max_instances 3 --travelplanner_home /path/to/TravelPlanner_official
python scripts/evaluation/run_travelplanner_repair.py --split validation --max_instances 3 --travelplanner_home /path/to/TravelPlanner_official

# Release matrix / validation orchestration
python scripts/evaluation/run_travelplanner_release_matrix.py --run-validation --workers 20 --travelplanner-home /path/to/TravelPlanner_official

# Generate test-set submissions
python scripts/evaluation/run_travelplanner_test_submit.py --mode bdi-repair --output_dir runs/tp_test_submit --workers 100
```

TravelPlanner requires an external checkout of the official repo. It is **not** stored in this repo.
Supply the path via the `TRAVELPLANNER_HOME` environment variable or the `--travelplanner_home` CLI flag.
The checkout must contain the official database files, and the Hugging Face `osunlp/TravelPlanner` dataset
must be accessible.

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
- `planbench_data/planner_tools/VAL/validate`

If local symbolic verification fails on macOS, check executable permissions:

```bash
chmod +x planbench_data/planner_tools/VAL/validate
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
5. `travelplanner/official.py` evaluates it with the official evaluator from the external TravelPlanner checkout (path from `TRAVELPLANNER_HOME`)
6. `travelplanner/runner.py` handles checkpointing, summaries, and optional MLflow logging

Repair is split into two layers:
- **non-oracle repair** uses deterministic local critique / patch guardrails from `travelplanner/review.py`
- **oracle repair** uses evaluator feedback during `bdi-repair` evaluation mode

`TRAVELPLANNER_BDI_PROMPT_VERSION` selects the BDI prompt stack in `travelplanner/engine.py`.
Current code defaults to `v3`; `v4` remains available as an experimental path.

### 8. Other active subsystems

- `scripts/replanning/run_dynamic_replanning.py` + `src/bdi_llm/dynamic_replanner/` — execution-aware replanning after grounded-action failure

## Data and artifact conventions

- `planbench_data/` — current PDDL benchmark assets and VAL binary
- TravelPlanner official checkout — external repo, NOT stored here; path supplied via `TRAVELPLANNER_HOME` or `--travelplanner_home`
- `runs/` — mutable checkpoints, scratch outputs, and MLflow data (`runs/mlflow/`)
- `artifacts/paper_eval_20260213/` — frozen paper evidence snapshot; do not edit or treat mutable reruns as replacements for paper numbers
- `RESULTS_PROVENANCE.md` — exact source files for every benchmark number in README; update when regenerating results

## Project automation and docs (non-runtime)

- `scripts/ralph/` — Ralph autonomous agent executor (PRD-driven task decomposition with quality gates)
  - `scripts/ralph/CLAUDE.md` is a nested instruction file Claude Code auto-loads when working under `scripts/ralph/`. It defines a per-story execute → quality-check → commit loop and does not override this root CLAUDE.md.
- `paper_icml2026/` — ICML paper artifacts (figures, sections, compiled paper)
- `docs/conductor/` — documentation hub (product, workflow, tech stack, tracks)
- `docs/c4/` — C4 architecture diagrams (context, container, component)

## Known repo gotcha — PlanBench assets dual layout (by design)

There are **two** PlanBench asset trees in this repo. Both are real and serve
different deployment paths — neither is "stale". Pick the right one for the
context:

- **`workspaces/planbench_data/`** — the path used by the **Python runtime**:
  - `src/bdi_llm/config.py` `_default_val_path` defaults here.
  - `src/bdi_llm/symbolic_verifier.py` docstring documents this default.
  - `tests/integration/*` and `tests/unit/test_domain_spec.py` reference it.
  - `bridges2_sbatch_under_review/bdi_env.env` `VAL_VALIDATOR_PATH` points here.
  - This is what gets used for any `python scripts/...` invocation on a
    local machine or on Bridges2.
- **`planbench_data/`** (repo root) — the path used **only by the Docker image**:
  - `Dockerfile` `COPY planbench_data /app/planbench_data` copies this tree
    into the container.
  - Inside the container, `ENV VAL_VALIDATOR_PATH=/app/planbench_data/...`
    overrides the Python default.
  - The host-side path is never read at runtime by the Python code; it
    exists purely as a Docker build context.

**Practical implications**:

- If a runner reports `VAL validator not found at: planbench_data/...`, the
  problem is that the env var (or `--val_path` CLI arg) is pointing at the
  wrong layout for the runtime in use. On Bridges2 / local Python,
  `VAL_VALIDATOR_PATH` must point under `workspaces/planbench_data/`. Inside
  the Docker container, it must point under `/app/planbench_data/`.
- If you `git mv` either tree to consolidate, you must also update every
  reference in `src/`, `tests/`, `Dockerfile`, `bridges2_sbatch_under_review/`,
  README, and docs. Do not consolidate as a casual cleanup — both trees are
  load-bearing for their respective deployment paths.

## Bridges2 / PSC deployment lessons

These are the current known-good constraints and failure modes for running this
repo on PSC Bridges2.

### 1. Storage placement rules

- Treat `/ocean/projects/cis260113p/zjiang9/` as the only valid home for
  project environments, caches, logs, and mutable artifacts.
- Do **not** install project dependencies into `HOME` on Bridges2.
- Redirect at least these paths to `/ocean`:
  - `PIP_CACHE_DIR`
  - `CONDA_PKGS_DIRS`
  - `HF_HOME`
  - `HF_HUB_CACHE`
  - `TMPDIR`
  - `PYTHONUSERBASE`
- `HOME` on Bridges2 is quota-constrained; large `pip` / HF caches can fill it
  quickly and break installs with `Disk quota exceeded`.

### 2. Job partition split

- Environment creation / package installation should run on CPU partitions
  first, then model serving / eval should run on GPU partitions.
- For Bridges2 `RM-shared`, respect the partition's memory-per-core cap.
  Avoid requests whose implied memory-per-core exceeds `2000M/core`.
- When a workflow has a CPU setup phase and a GPU serve/eval phase, submit them
  as separate jobs with Slurm dependencies.

### 3. Git sync discipline

- When syncing work from local to the Bridges2 checkout, use Git only.
- Do **not** manually copy directories or overwrite the remote worktree outside
  Git.
- If the Bridges2 repo is already dirty, preserve unrelated changes and update
  only the intended paths via `git fetch` plus targeted checkout/stash flows.

### 4. GLM-4.7-Flash on Bridges2: host install findings

- `zai-org/GLM-4.7-Flash` does not work with older stable combinations such as
  `vllm 0.11.2 + transformers 4.57.x`; the model architecture
  `glm4_moe_lite` is not recognized there.
- Updating only `transformers` is insufficient; older `vllm` builds fail later
  on tokenizer/runtime compatibility.
- The Hugging Face model card recommendation (`vLLM` main/nightly +
  `transformers` main) is logically correct for model support, but **direct
  host-side deployment on Bridges2 fails for system reasons**:
  - host `glibc` is `2.28`
  - latest precompiled `vllm` components require newer `glibc`
  - newer stacks may also expect a newer NVIDIA driver than the host exposes
- In other words: on Bridges2, the blocker is not the model card itself, but
  the host runtime ABI / driver floor.

### 5. PSC-supported path that is most promising

- Prefer `Apptainer` / `Singularity` on Bridges2 for new LLM serving work.
- PSC officially supports these container workflows and provides NGC-backed
  containers under `/ocean/containers/`.
- For this repo, the most relevant current base image is:
  - `/ocean/containers/ngc/pytorch/pytorch_25.02-py3.sif`
- This image has a newer userspace (`glibc 2.39`) and was verified to expose
  the GPU successfully under `apptainer exec --nv`, including
  `torch.cuda.is_available() == True` on an H100 node.
- PSC's prebuilt AI module environments are currently too old for
  `GLM-4.7-Flash`, and the visible NIM catalog on Bridges2 is not a ready-made
  general LLM serving path for this model.

### 6. Current Bridges2 helper scripts

- Host-oriented scripts live under `bridges2_sbatch_under_review/`:
  - `psc_ocean_env.sh`
  - `install_bdi_llm.sbatch`
  - `run_eval_glm47flash_paperaligned.sbatch`
  - `aggregate_planbench_glm47flash_paperaligned.sbatch`
- Container-oriented scripts also live there:
  - `psc_apptainer_env.sh`
  - `install_glm47flash_apptainer.sbatch`

### 7-11. Detailed deployment SOPs and debugging gotchas

Moved to `.claude/rules/psc-deployment.md` (auto-loaded). Covers operational gotchas, GLM-4.7-Flash deployment + API alignment, deployment debug log, and Qwen3.6-35B-A3B deployment.

