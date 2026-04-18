---
title: "Functional Flow"
description: "Current mainline runtime whitepaper for engineers inheriting the repository."
citation_style: "file path + symbol name"
scope: "current mainline runtime only"
---

# Functional Flow

This page documents how the repository works **today**.

It is a runtime whitepaper for engineers inheriting the codebase, not a benchmark scoreboard and not a historical archive. The source of truth for this page is the current runtime scope in `CLAUDE.md`, plus the active implementation under:

- `src/bdi_llm/`
- `src/interfaces/`
- `scripts/evaluation/`
- `scripts/replanning/`
- `scripts/swe_bench/`

This page does **not** treat these as default mainline runtime truth:

- `workspaces/pnsv_workspace/` — architecture/reference workspace, not the default import path used by current runners

This page also intentionally does **not** duplicate benchmark tables. Use these instead:

- `docs/BENCHMARKS.md` — high-level benchmark surfaces and current summary pointers
- `RESULTS_PROVENANCE.md` — exact source files for reported benchmark numbers
- `README.md` — user-facing benchmark snapshot and TravelPlanner release notes

## 1. Current mainline runtime at a glance

| Surface | What is current | Primary anchors |
| --- | --- | --- |
| Shared planning / verification substrate | Main runtime library used by the active runners | `src/bdi_llm/planning_task.py -> PlanningTask`, `src/bdi_llm/schemas.py -> BDIPlan`, `src/bdi_llm/planner/domain_spec.py -> DomainSpec`, `src/bdi_llm/planner/bdi_engine.py -> BDIPlanner`, `src/bdi_llm/verifier.py -> PlanVerifier`, `src/bdi_llm/symbolic_verifier.py -> PDDLSymbolicVerifier`, `src/bdi_llm/symbolic_verifier.py -> IntegratedVerifier` |
| Generic PDDL / PlanBench-style runtime | Primary PDDL entrypoints | `scripts/evaluation/run_generic_pddl_eval.py -> main`, `scripts/evaluation/run_generic_pddl_eval.py -> run_evaluation`, `scripts/evaluation/run_planbench_paperaligned.py -> main` |
| TravelPlanner runtime | First-class non-PDDL runtime | `scripts/evaluation/run_travelplanner_eval.py -> main`, `src/bdi_llm/travelplanner/runner.py -> run_split`, `scripts/evaluation/run_travelplanner_release_matrix.py -> main`, `scripts/evaluation/run_travelplanner_test_submit.py -> main` |
| Interfaces | Thin user / agent-facing surfaces | `src/interfaces/cli.py -> main`, `src/interfaces/mcp_server.py -> generate_plan`, `src/interfaces/mcp_server.py -> verify_plan`, `src/interfaces/mcp_server.py -> execute_verified_plan` |
| Secondary active subsystems | Active, but not the main benchmark narrative | `scripts/replanning/run_dynamic_replanning.py -> run_dynamic_replanning_eval`, `scripts/swe_bench/run_swe_bench_batch.py -> main` |

The architectural center of the current runtime is the **shared substrate**, not any single benchmark runner. The runners are entrypoints layered on top of that substrate.

## 2. Shared runtime substrate

### 2.1 `PlanningTask` is the normalized planner input contract

The repository’s active runtimes normalize incoming benchmark data into a shared task contract:

- `src/bdi_llm/planning_task.py -> PlanningTask`
- `src/bdi_llm/planning_task.py -> TaskAdapter`
- `src/bdi_llm/planning_task.py -> PlanSerializer`

For generic PDDL, the active built-in implementations are:

- `src/bdi_llm/planning_task.py -> PDDLTaskAdapter`
- `src/bdi_llm/planning_task.py -> PDDLPlanSerializer`

For TravelPlanner, the adapter is separate but still targets the same input abstraction:

- `src/bdi_llm/travelplanner/adapter.py -> TravelPlannerTaskAdapter`

This is the first major boundary in the current runtime: benchmark-native input gets normalized **before** it reaches the planner.

### 2.2 `BDIPlan` is the core intermediate plan representation for the PDDL side

The generic PDDL side centers on:

- `src/bdi_llm/schemas.py -> ActionNode`
- `src/bdi_llm/schemas.py -> DependencyEdge`
- `src/bdi_llm/schemas.py -> BDIPlan`
- `src/bdi_llm/schemas.py -> BDIPlan.to_networkx`
- `src/bdi_llm/schemas.py -> BDIPlan.from_llm_text`

`BDIPlan` is the DAG-shaped intermediate representation that the structural verifier understands and that the PDDL serializer converts back into grounded actions.

TravelPlanner is explicitly different: it is a separate itinerary-shaped runtime and does **not** use `BDIPlan` as its output contract.

### 2.3 `DomainSpec` separates built-in domains from arbitrary PDDL domains

The domain abstraction layer lives in:

- `src/bdi_llm/planner/domain_spec.py -> DomainSpec`
- `src/bdi_llm/planner/domain_spec.py -> DomainSpec.from_pddl`
- `src/bdi_llm/planner/domain_spec.py -> extract_domain_name_from_pddl`
- `src/bdi_llm/planner/domain_spec.py -> extract_actions_from_pddl`
- `src/bdi_llm/planner/domain_spec.py -> build_domain_context`

This layer is what allows the current runtime to support both:

- built-in domains such as blocksworld / logistics / depots, and
- arbitrary PDDL domains loaded from a `domain.pddl`

without hardcoding everything inside the planner constructor.

### 2.4 `BDIPlanner` is the main generation module

The main planner entrypoint is:

- `src/bdi_llm/planner/bdi_engine.py -> BDIPlanner`
- `src/bdi_llm/planner/bdi_engine.py -> BDIPlanner.generate_plan`
- `src/bdi_llm/planner/bdi_engine.py -> BDIPlanner.forward`
- `src/bdi_llm/planner/bdi_engine.py -> BDIPlanner.repair_from_val_errors`

Important current-runtime nuance:

- `BDIPlanner.generate_plan()` is the plain generation entrypoint.
- `BDIPlanner.forward()` wraps generation with structural verification and optional graph repair.
- The current generic PDDL runner primarily calls `generate_plan()` and orchestrates serialization, structural checks, VAL checks, and artifact persistence in the runner itself.

So the architecture is runner-on-top-of-shared-planner, not “the planner does everything internally.”

### 2.5 Verification is layered, and the layers should not be conflated

Structural verification is in:

- `src/bdi_llm/verifier.py -> VerificationResult`
- `src/bdi_llm/verifier.py -> PlanVerifier.verify`
- `src/bdi_llm/verifier.py -> PlanVerifier.topological_sort`

Its contract is intentionally narrow:

- empty graph = hard failure
- cycle = hard failure
- disconnected components = warning, not a blocker

Symbolic / domain verification is in:

- `src/bdi_llm/symbolic_verifier.py -> PDDLSymbolicVerifier`
- `src/bdi_llm/symbolic_verifier.py -> BlocksworldPhysicsValidator`
- `src/bdi_llm/symbolic_verifier.py -> IntegratedVerifier`
- `src/bdi_llm/symbolic_verifier.py -> IntegratedVerifier.verify_full`
- `src/bdi_llm/symbolic_verifier.py -> IntegratedVerifier.build_planner_feedback`

The practical division is:

- `PlanVerifier` checks graph shape only
- `PDDLSymbolicVerifier` checks PDDL executability through `VAL`
- `IntegratedVerifier` is the combined multi-layer abstraction for callers that want a unified report and repair-oriented feedback

In the current generic PDDL runner, the mainline path uses `PlanVerifier` and `PDDLSymbolicVerifier` directly, then reuses `IntegratedVerifier.build_planner_feedback()` to compress verifier failures into repair prompts.

## 3. Current generic PDDL / PlanBench-style runtime

This is the current **mainline PDDL runtime**. The default entrypoints are:

- `scripts/evaluation/run_generic_pddl_eval.py -> main`
- `scripts/evaluation/run_generic_pddl_eval.py -> run_evaluation`
- `scripts/evaluation/run_generic_pddl_eval.py -> _evaluate_worker`

### 3.1 Main entrypoints

The current primary generic runner is:

- `scripts/evaluation/run_generic_pddl_eval.py -> main`

It exposes two execution modes:

- `GENERATE_ONLY`
- `VERIFY_WITH_VAL`

There is also an active built-in PlanBench runner:

- `scripts/evaluation/run_planbench_paperaligned.py -> main`

That second script is the supported built-in-domain surface for paper-aligned `baseline` / `bdi` / `bdi-repair` reporting. It complements the generic PDDL adapter / serializer runtime rather than replacing it.

### 3.2 Mainline generic PDDL flow

The current generic flow is:

1. **Read the PDDL domain and derive runtime domain metadata**
   - `scripts/evaluation/run_generic_pddl_eval.py -> run_evaluation`
   - `src/bdi_llm/planner/domain_spec.py -> extract_domain_name_from_pddl`
   - `src/bdi_llm/planner/domain_spec.py -> extract_actions_from_pddl`
   - `src/bdi_llm/planner/domain_spec.py -> DomainSpec.from_pddl`

   The runner extracts the domain name, action schema, prompt-facing `domain_context`, and parameter order map from the domain file.

2. **Normalize each problem into a `PlanningTask`**
   - `scripts/evaluation/run_generic_pddl_eval.py -> _evaluate_worker`
   - `src/bdi_llm/planning_task.py -> PDDLTaskAdapter.to_planning_task`

   The adapter converts `:objects`, `:init`, and `:goal` into planner-facing `beliefs` and `desire`, while attaching the derived `domain_context`.

3. **Generate a `BDIPlan`**
   - `src/bdi_llm/planner/bdi_engine.py -> BDIPlanner.generate_plan`
   - `src/bdi_llm/schemas.py -> BDIPlan`

4. **Serialize the plan back into grounded PDDL actions**
   - `src/bdi_llm/planning_task.py -> PDDLPlanSerializer.from_bdi_plan`

   This is where the DAG-shaped plan becomes a sequential grounded action list again.

5. **Run structural verification**
   - `src/bdi_llm/verifier.py -> PlanVerifier.verify`

6. **Optionally run symbolic verification through `VAL`**
   - `src/bdi_llm/symbolic_verifier.py -> PDDLSymbolicVerifier.verify_plan`

7. **If VAL fails, optionally repair using verifier-guided feedback**
   - `src/bdi_llm/symbolic_verifier.py -> IntegratedVerifier.build_planner_feedback`
   - `src/bdi_llm/planner/bdi_engine.py -> BDIPlanner.repair_from_val_errors`

8. **Persist artifacts under `runs/`**
   - `scripts/evaluation/run_generic_pddl_eval.py -> run_evaluation`

   The current runner writes:
   - `raw_predictions.jsonl`
   - `results.json`
   - `summary.json`

   under `runs/generic_pddl_eval/<timestamp>/`.

### 3.3 Where `run_planbench_paperaligned.py` fits

`run_planbench_paperaligned.py` is the supported built-in PlanBench entrypoint for paper-aligned reporting.

Its key anchor is:

- `scripts/evaluation/run_planbench_paperaligned.py -> main`

Unlike the generic runner, it is specialized for built-in PlanBench domains and records `baseline_result`, `bdi_initial_result`, and `bdi_repair_result` in one pass. That makes it the right operational anchor for built-in-domain PlanBench reruns, while `run_generic_pddl_eval.py` remains the architecture anchor for arbitrary PDDL domains.

## 4. Current TravelPlanner runtime

TravelPlanner is now a **first-class mainline runtime surface**, parallel to generic PDDL rather than subordinate to it.

It should be understood as a separate non-PDDL pipeline whose active runtime lives under:

- `src/bdi_llm/travelplanner/`

The most important runtime fact is simple:

- TravelPlanner uses `PlanningTask` for normalized input, but it does **not** use `BDIPlan` as its output contract.
- Its output is an itinerary that gets serialized into the official TravelPlanner row format.

### 4.1 Main entrypoints

The current TravelPlanner runtime surfaces are:

- `scripts/evaluation/run_travelplanner_eval.py -> main`
- `src/bdi_llm/travelplanner/runner.py -> generate_submission`
- `src/bdi_llm/travelplanner/runner.py -> evaluate_sample`
- `src/bdi_llm/travelplanner/runner.py -> run_split`
- `scripts/evaluation/run_travelplanner_release_matrix.py -> main`
- `scripts/evaluation/run_travelplanner_test_submit.py -> main`

`run_travelplanner_eval.py` is the current validation runner surface. The real orchestration lives in `travelplanner/runner.py`.

### 4.2 TravelPlanner flow

The current TravelPlanner flow is:

1. **Load official benchmark samples**
   - `src/bdi_llm/travelplanner/official.py -> load_travelplanner_split`

2. **Normalize a sample into `PlanningTask` and inject the output contract**
   - `src/bdi_llm/travelplanner/adapter.py -> TravelPlannerTaskAdapter`
   - `src/bdi_llm/travelplanner/adapter.py -> TravelPlannerTaskAdapter.to_planning_task`
   - `src/bdi_llm/travelplanner/spec.py -> load_travelplanner_spec`
   - `src/bdi_llm/travelplanner/spec.md`

   The adapter builds `beliefs` from the query plus sandbox/reference information, and injects the TravelPlanner output contract into `domain_context`.

3. **Generate an itinerary**
   - `src/bdi_llm/travelplanner/engine.py -> TravelPlannerGenerator`
   - `src/bdi_llm/travelplanner/engine.py -> TravelPlannerGenerator.generate_baseline`
   - `src/bdi_llm/travelplanner/engine.py -> TravelPlannerGenerator.generate_bdi`

4. **Optionally run non-oracle local repair**
   - `src/bdi_llm/travelplanner/engine.py -> TravelPlannerGenerator.run_non_oracle_repair`
   - `src/bdi_llm/travelplanner/review.py -> critique_itinerary`
   - `src/bdi_llm/travelplanner/review.py -> assess_patch_scope`
   - `src/bdi_llm/travelplanner/review.py -> apply_patch`

   This is the deterministic local critique / patch-guardrail layer used in `bdi-repair`.

5. **Serialize the itinerary into official submission rows**
   - `src/bdi_llm/travelplanner/serializer.py -> TravelPlannerPlanSerializer`
   - `src/bdi_llm/travelplanner/serializer.py -> TravelPlannerPlanSerializer.to_submission_record`

6. **Evaluate with the official evaluator**
   - `src/bdi_llm/travelplanner/official.py -> resolve_travelplanner_home`
   - `src/bdi_llm/travelplanner/official.py -> load_official_evaluator`
   - `src/bdi_llm/travelplanner/official.py -> evaluate_travelplanner_plan`

7. **Optionally run validation-only oracle repair**
   - `src/bdi_llm/travelplanner/runner.py -> build_evaluator_feedback`
   - `src/bdi_llm/travelplanner/engine.py -> TravelPlannerGenerator.run_oracle_repair`

   In the current design, oracle repair happens only after an official validation failure and is not the default test-time generation path.

8. **Persist split outputs, checkpoints, and summaries**
   - `src/bdi_llm/travelplanner/runner.py -> _write_checkpoint`
   - `src/bdi_llm/travelplanner/runner.py -> run_split`

### 4.3 Default vs experimental TravelPlanner behavior

The current default BDI prompt selection is controlled by:

- `src/bdi_llm/travelplanner/engine.py -> TravelPlannerGenerator.__init__`

The important current-mainline behavior is:

- default prompt version = `v3`
- `legacy` is retained as a compatibility path
- `v4` exists as an experimental two-stage checklist/render path

The release orchestration surface makes this explicit:

- `scripts/evaluation/run_travelplanner_release_matrix.py -> main`

That script pins:

- `TRAVELPLANNER_BDI_PROMPT_VERSION='v3'`

So for current mainline release guidance, `v3` is the default, while `v4` remains experimental.

### 4.4 Validation vs test-submission behavior

This distinction matters for handoff:

- `src/bdi_llm/travelplanner/runner.py -> evaluate_sample` is the validation path that can use official-evaluator feedback for an oracle repair pass.
- `scripts/evaluation/run_travelplanner_test_submit.py -> main` reuses `src/bdi_llm/travelplanner/runner.py -> generate_submission` and follows the same non-oracle generation / local repair path, but it does **not** use validation-only oracle repair.

That split is part of the current runtime truth and should remain explicit in the docs.

## 5. Active but secondary surfaces

These surfaces are active and important, but they are not the center of the repository’s mainline benchmark narrative.

### 5.1 CLI demo

The local CLI demo lives at:

- `src/interfaces/cli.py -> main`

It is a thin demonstration surface over `BDIPlanner` plus `PlanVerifier`, not an architecture-defining runtime in its own right.

### 5.2 MCP server

The MCP server lives at:

- `src/interfaces/mcp_server.py -> generate_plan`
- `src/interfaces/mcp_server.py -> verify_plan`
- `src/interfaces/mcp_server.py -> execute_verified_plan`

This is a thin interface layer over the planner / verifier stack. `execute_verified_plan` is the gated-execution surface: it only executes the requested shell command after symbolic plan verification succeeds.

### 5.3 Dynamic replanning

Execution-aware replanning lives at:

- `scripts/replanning/run_dynamic_replanning.py -> generate_and_replan`
- `scripts/replanning/run_dynamic_replanning.py -> run_dynamic_replanning_eval`
- `src/bdi_llm/dynamic_replanner/executor.py -> PlanExecutor.execute`
- `src/bdi_llm/dynamic_replanner/replanner.py -> DynamicReplanner.generate_recovery_plan`

This path is distinct from the static verify-repair loops used by the generic PDDL runner. It executes prefixes, captures the exact failing action, and asks the replanner for a recovery suffix.

### 5.4 SWE-bench / coding planner path

The coding-domain path lives at:

- `scripts/swe_bench/run_swe_bench_batch.py -> main`
- `scripts/swe_bench/swe_bench_harness.py -> LocalSWEBenchHarness`
- `src/bdi_llm/coding_planner.py -> CodingBDIPlanner`

This is an active subsystem for SWE-bench-style local repository execution. It is real runtime code, but it should be described as a secondary surface rather than as the mainline architectural center.

## 6. Data, artifacts, and provenance boundaries

The current runtime expects these storage boundaries:

| Path | Role in the current runtime |
| --- | --- |
| `workspaces/planbench_data/` | Current PDDL benchmark assets and local `VAL` binary |
| `workspaces/TravelPlanner_official/` | Official TravelPlanner checkout used by the evaluator path |
| `runs/` | Mutable checkpoints, outputs, summaries, and scratch artifacts |
| `artifacts/paper_eval_20260213/` | Frozen paper snapshot; not the mutable source of truth for current reruns |

Two important handoff rules follow from this:

1. The current mainline runtime resolves PDDL assets under `workspaces/planbench_data/`, not a root-level `planbench_data/` tree.
2. Benchmark numbers belong in provenance-facing docs, not in this whitepaper.

For reported numbers and their sources, use:

- `docs/BENCHMARKS.md`
- `RESULTS_PROVENANCE.md`
- `README.md`

## 7. Handoff guidance: where to start reading

If you are debugging or extending the current runtime, start here:

### Generic PDDL issue

1. `scripts/evaluation/run_generic_pddl_eval.py -> main`
2. `scripts/evaluation/run_generic_pddl_eval.py -> run_evaluation`
3. `src/bdi_llm/planning_task.py -> PDDLTaskAdapter`
4. `src/bdi_llm/planner/domain_spec.py -> DomainSpec.from_pddl`
5. `src/bdi_llm/planner/bdi_engine.py -> BDIPlanner`
6. `src/bdi_llm/verifier.py -> PlanVerifier`
7. `src/bdi_llm/symbolic_verifier.py -> PDDLSymbolicVerifier`

### TravelPlanner issue

1. `scripts/evaluation/run_travelplanner_eval.py -> main`
2. `src/bdi_llm/travelplanner/runner.py -> run_split`
3. `src/bdi_llm/travelplanner/adapter.py -> TravelPlannerTaskAdapter`
4. `src/bdi_llm/travelplanner/engine.py -> TravelPlannerGenerator`
5. `src/bdi_llm/travelplanner/review.py -> critique_itinerary`
6. `src/bdi_llm/travelplanner/serializer.py -> TravelPlannerPlanSerializer`
7. `src/bdi_llm/travelplanner/official.py -> evaluate_travelplanner_plan`

### Interface / agent issue

1. `src/interfaces/mcp_server.py`
2. `src/interfaces/cli.py`
3. then the shared substrate in `src/bdi_llm/`

Only after that should you drop into `workspaces/pnsv_workspace/`.

## Appendix. Reference-only areas

### `workspaces/pnsv_workspace/`

`workspaces/pnsv_workspace/` is retained architecture/reference material, not the current operational runtime. The key anchors are:

- `workspaces/pnsv_workspace/src/core/bdi_engine.py -> BDIEngine`
- `workspaces/pnsv_workspace/src/core/verification_bus.py -> BaseDomainVerifier`

This workspace is valuable if you are studying the cleaner dependency-injected architecture or planning a future refactor. It is not the default import/runtime path used by the current generic PDDL runner, TravelPlanner runner, MCP server, dynamic replanning path, or SWE-bench harness.

If you are inheriting the codebase to fix a real production or evaluation issue, read the mainline runtime first and the reference workspace second.
