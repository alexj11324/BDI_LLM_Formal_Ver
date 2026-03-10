# Methods Section — Skeleton Draft

> **Scope note:** This section describes the shared planning and verification substrate that underlies the PNSV framework. It does **not** contain benchmark headline numbers — those appear in the Results sections (§4–5). All architectural claims are sourced from the substrate_packet and grounded in `docs/FUNCTIONAL_FLOW.md` and the `src/bdi_llm/` implementation.

---

## 3. Method

The central design principle of PNSV is a **shared substrate** rather than a collection of benchmark-specific pipelines. All active runtimes — formal PDDL evaluation, real-constraint TravelPlanner evaluation, SWE-bench (appendix) — are thin entrypoints layered on top of a common planning, verification, and repair core. This section describes the five major substrate components and their interaction.

### 3.1 Normalized Task Contract (`PlanningTask`)

Before any plan generation, benchmark-native inputs are normalized into a common dataclass:

```
PlanningTask(task_id, domain_name, beliefs, desire, domain_context?, metadata)
```

Two abstract boundaries enforce this separation:

- **`TaskAdapter`** — converts benchmark-native data (e.g., raw PDDL problem text, TravelPlanner query) *into* a `PlanningTask`.
- **`PlanSerializer`** — converts planner output *back* into benchmark-native format (e.g., grounded PDDL action sequences, TravelPlanner submission rows).

On the PDDL side, `PDDLTaskAdapter.to_planning_task()` parses `:objects`, `:init`, and `:goal` blocks into prompt-facing `beliefs` and `desire` strings, while attaching the domain's action schema as `domain_context`. On the TravelPlanner side, a separate `TravelPlannerTaskAdapter` targets the same `PlanningTask` abstraction but injects the TravelPlanner output contract instead.

> **Source:** `src/bdi_llm/planning_task.py` → `PlanningTask`, `TaskAdapter`, `PlanSerializer`, `PDDLTaskAdapter`. `src/bdi_llm/travelplanner/adapter.py` → `TravelPlannerTaskAdapter`.

### 3.2 Plan Representation (`BDIPlan`)

For the PDDL side, the intermediate plan representation is `BDIPlan`, a Pydantic model comprising:

- **`ActionNode`** — an atomic action (intention) with `id`, `action_type`, `params`, and `description`.
- **`DependencyEdge`** — a directed dependency (`source` → `target`) encoding execution ordering.
- **`BDIPlan`** — the complete plan graph, with helper methods to convert from raw LLM JSON text (`from_llm_text`) and into a NetworkX digraph (`to_networkx`) for verification.

`BDIPlan` is explicitly a DAG-shaped representation that the structural verifier can analyze and that the PDDL serializer converts back into grounded action lists via topological sorting.

> **Important boundary:** TravelPlanner does **not** use `BDIPlan` as its output contract. Its output is an itinerary-shaped structure serialized into the official TravelPlanner row format. The shared substrate connects TravelPlanner at the `PlanningTask` level (input normalization) but not at the intermediate plan representation level.

> **Source:** `src/bdi_llm/schemas.py` → `ActionNode`, `DependencyEdge`, `BDIPlan`. Boundary note: `docs/FUNCTIONAL_FLOW.md` §2.2.

### 3.3 Domain Abstraction (`DomainSpec`)

`DomainSpec` is an immutable configuration object that bundles all domain-specific metadata for the planner:

- Valid action types and required parameters
- DSPy `Signature` class for structured generation
- Optional few-shot demonstration loader
- Optional raw PDDL text and derived `domain_context`

Two construction paths cover the domain spectrum:

1. **`DomainSpec.from_name()`** — for built-in domains (blocksworld, logistics, depots) with pre-registered signatures, parameter schemas, and optional demos.
2. **`DomainSpec.from_pddl()`** — for arbitrary PDDL domains, where `extract_actions_from_pddl()` parses action names, typed parameters, preconditions, and add/delete effects from raw domain text, and `build_domain_context()` renders that schema into a human-readable prompt block.

This layer decouples domain knowledge from the planner constructor, enabling evaluation on novel domains without code changes.

> **Design decision:** For arbitrary PDDL domains, `DomainSpec.from_pddl()` sets `required_params = {}` and relies on downstream VAL verification (Layer 2) for parameter validation rather than enforcing schema constraints at the planner layer.

> **Source:** `src/bdi_llm/planner/domain_spec.py` → `DomainSpec`, `extract_actions_from_pddl`, `build_domain_context`.

### 3.4 Plan Generation (`BDIPlanner`)

`BDIPlanner` is the main generation module, built on DSPy. It resolves a `DomainSpec`, instantiates a DSPy generation program from the spec's signature class, and optionally loads few-shot demos.

Two public interfaces serve different orchestration patterns:

- **`generate_plan(beliefs, desire, domain_context?)`** — the plain generation entrypoint. For generic domains, it requires non-empty `domain_context` (either passed explicitly or stored in the `DomainSpec`).
- **`forward(beliefs, desire, domain_context?)`** — wraps generation with action-constraint checking, structural verification via `PlanVerifier`, and optional graph auto-repair. Returns the plan even when structurally invalid, so external repair layers can handle it.

The architecture is **runner-on-top-of-shared-planner**: the current mainline generic PDDL runner (`run_generic_pddl_eval.py`) calls `generate_plan()` directly and orchestrates serialization, structural checks, VAL checks, and artifact persistence in the runner itself, rather than relying on `forward()` alone.

> **Source:** `src/bdi_llm/planner/bdi_engine.py` → `BDIPlanner`, `generate_plan`, `forward`. Architecture note: `docs/FUNCTIONAL_FLOW.md` §2.4.

### 3.5 Layered Verification

Verification is intentionally decomposed into three layers that must not be conflated:

#### Layer 1: Structural Verification (`PlanVerifier`)

Checks graph shape only, with a narrow contract:

| Check | Severity | Description |
| --- | --- | --- |
| Empty graph | **Hard failure** | Plan contains no actions |
| Cycles | **Hard failure** | No valid topological execution order exists |
| Disconnected components | **Warning** | May represent valid parallel subplans; deferred to Layer 2 |

Returns a `VerificationResult` separating `hard_errors` from `warnings`. Hard errors block execution and prevent Layer 2 from running.

> **Design choice:** Disconnected components are *warnings* rather than blockers. This reflects the observation that valid plans may contain independent parallel subplans whose executability should be judged by the symbolic verifier.

#### Layer 2: Symbolic Verification (`PDDLSymbolicVerifier`)

Delegates PDDL executability checking to the external VAL (Validating Action Language) tool. `PDDLSymbolicVerifier.verify_plan()` is a thin wrapper around the `run_val` subprocess: it checks precondition satisfaction, effect application, and goal reachability.

VAL runs only when Layer 1 reports no hard errors. This gating prevents wasted symbolic computation on malformed plan graphs.

#### Layer 3: Domain-Specific Validation (optional)

A pluggable third layer for additional semantic constraints that VAL may not capture. The current implementation registers a `BlocksworldPhysicsValidator` that simulates action effects and checks physical rules (e.g., can only pick up clear blocks, hand holds at most one block). Other domains may have no extra validator.

> **Non-claim:** This layer is not universally present. Currently, only Blocksworld has a registered physics validator. The architecture is pluggable, but not all domains exercise it.

#### Integrated Verifier

`IntegratedVerifier.verify_full()` composes all three layers into a single report structure:

```
{
  layers: { structural: {...}, symbolic: {...}, physics: {...} },
  overall_valid: bool,
  error_summary: str,
  planner_feedback: {...}
}
```

`IntegratedVerifier.build_planner_feedback()` condenses failed layers and key errors into repair-oriented diagnostics: it separates structural, symbolic, and physics repair priorities and extracts VAL-specific repair advice for the planner.

> **Runner nuance:** In the current mainline PDDL runtime, the runner invokes `PlanVerifier` and `PDDLSymbolicVerifier` directly, then reuses `IntegratedVerifier.build_planner_feedback()` to compress failures into repair prompts. `IntegratedVerifier.verify_full()` is available as the unified abstraction, but the runner may call lower layers individually for orchestration flexibility.

> **Source:** `src/bdi_llm/verifier.py` → `PlanVerifier`, `VerificationResult`. `src/bdi_llm/symbolic_verifier.py` → `PDDLSymbolicVerifier`, `BlocksworldPhysicsValidator`, `IntegratedVerifier`.

### 3.6 Verifier-Guided Repair Loop

When verification fails, the framework closes a plan–verify–repair cycle:

1. `IntegratedVerifier.build_planner_feedback()` generates structured repair guidance identifying the failed layers, key errors, and VAL-specific repair advice.
2. `BDIPlanner.repair_from_val_errors()` re-generates the plan incorporating the verifier feedback, cumulative repair history (all prior attempts), and structured verification diagnostics.
3. The runner iterates: generate → verify → compress feedback → repair → re-verify, up to a configurable maximum iteration count.

The repair module includes early-exit logic: if the VAL error signature repeats across consecutive attempts (detected via hash-based pattern matching), the loop terminates to avoid wasting inference budget on non-convergent repairs.

#### Non-PDDL Repair (TravelPlanner)

On TravelPlanner, a separate repair pipeline applies:

- **Non-oracle local repair:** Deterministic critique/patch-guardrail layer (`critique_itinerary`, `assess_patch_scope`, `apply_patch`) used in the `bdi-repair` mode. Available at both validation and test time.
- **Oracle repair:** Uses official evaluator feedback (available only during validation evaluation, not at test time) to guide repair.

This distinction is critical for deployment-aligned claims: only non-oracle repair is available in the official test submission path.

> **Source:** `src/bdi_llm/planner/bdi_engine.py` → `repair_from_val_errors`. `src/bdi_llm/travelplanner/engine.py` → `run_non_oracle_repair`, `run_oracle_repair`. `src/bdi_llm/travelplanner/review.py` → `critique_itinerary`.

### 3.7 End-to-End Flow (Generic PDDL)

The mainline generic PDDL evaluation flow, orchestrated by `run_generic_pddl_eval.py` (current mainline runtime), proceeds as:

1. **Domain ingestion:** Read PDDL domain file → extract action schema → build `DomainSpec.from_pddl()`.
2. **Task normalization:** For each problem, `PDDLTaskAdapter.to_planning_task()` converts `:objects`, `:init`, `:goal` into a `PlanningTask`.
3. **Plan generation:** `BDIPlanner.generate_plan()` → `BDIPlan`.
4. **Plan serialization:** `PDDLPlanSerializer.from_bdi_plan()` topologically sorts the plan graph and emits grounded PDDL action sequences.
5. **Structural verification:** `PlanVerifier.verify()` → hard failures block further processing.
6. **Symbolic verification:** `PDDLSymbolicVerifier.verify_plan()` → VAL executability check.
7. **Repair (if VAL fails):** `IntegratedVerifier.build_planner_feedback()` → `BDIPlanner.repair_from_val_errors()` → re-verify (iterative).
8. **Artifact persistence:** Write `raw_predictions.jsonl`, `results.json`, `summary.json` under `runs/`.

> **Legacy boundary:** `scripts/evaluation/_legacy/run_planbench_full.py` is historical reference only and is **not** the current mainline runtime. `scripts/evaluation/run_verification_only.py` is an active supporting verification harness, but not the architectural center of the generic PDDL runtime.

> **Source:** `docs/FUNCTIONAL_FLOW.md` §3.

---

## Provenance compliance checklist for this document

- [x] No benchmark headline numbers appear in this section.
- [x] `run_generic_pddl_eval.py` described as current mainline runtime; `_legacy/run_planbench_full.py` explicitly excluded.
- [x] TravelPlanner `BDIPlan` non-use boundary explicitly stated (§3.2).
- [x] TravelPlanner oracle vs non-oracle repair distinction explicitly stated (§3.6).
- [x] Domain-specific physics validation described as optional and not universal (§3.5 Layer 3).
- [x] `IntegratedVerifier` described as available unifier, with runner-direct-invocation nuance noted (§3.5).
- [x] Terminology uses locked terms: shared substrate, layered verification, current mainline runtime.
- [x] SWE-bench not mentioned in methods section (appendix-only rule).
