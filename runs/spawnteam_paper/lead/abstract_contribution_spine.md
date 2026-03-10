# Abstract and Contribution Spine — Skeleton Draft

> **Provenance note:** All numbers in this draft are sourced from the pre-writing packets.
> PDDL numbers are from the current-mainline PlanBench snapshot (planbench_packet §4).
> TravelPlanner numbers are from the approved release surfaces (travelplanner_packet §4).
> These two evidence surfaces must never be merged into a single unlabeled claim.

---

## Abstract (skeleton)

Large language models (LLMs) can generate plausible natural-language plans, yet their outputs frequently violate the structural and semantic constraints required for executable deployment.
We present **Pluggable Neuro-Symbolic Verification (PNSV)**, a domain-agnostic framework built on a **shared planning and verification substrate** that normalizes heterogeneous planning tasks into a common contract, subjects LLM-generated plans to **layered verification** (structural → symbolic → domain-specific), and closes a **verifier-guided repair loop** that iteratively corrects failing plans using structured feedback.

The substrate is reused across two qualitatively different evidence surfaces:
(i) formal PDDL planning benchmarks (PlanBench), where the verify–repair loop lifts a collapsed logistics baseline from 0 / 572 to 572 / 572 and drives all five evaluated domains to 100 % under repair *(current-mainline snapshot)*;
(ii) the TravelPlanner travel-itinerary benchmark, where deployment-aligned non-oracle evaluation shows Final Pass Rate improving from 38.2 % (baseline) to 64.7 % (bdi-repair) on the official 1000-query test leaderboard *(official test submission)*.

By separating the verification substrate from benchmark-specific adapters, PNSV makes it practical to add formal guarantees to LLM planning without re-engineering the planner for each target domain.

---

## Contribution spine

### C1 — Shared planning and verification substrate

A domain-agnostic substrate comprising:
- **`PlanningTask`** — a normalized input contract that decouples the planner from benchmark-specific schemas via `TaskAdapter` / `PlanSerializer` boundaries.
- **`BDIPlan`** — a graph-structured intermediate plan representation (nodes + dependency edges) convertible to a NetworkX digraph for downstream verification.
- **`DomainSpec`** — an immutable domain abstraction that bundles valid action types, parameters, DSPy signature class, and optional raw PDDL text; supports both built-in domains (`from_name`) and arbitrary PDDL domains (`from_pddl`).
- **`BDIPlanner`** — the main generation module that resolves a `DomainSpec`, instantiates a DSPy generation program, and performs plan generation with optional structural repair.

> **Source:** substrate_packet §2, §4.

### C2 — Layered verification stack

A composable, three-layer verification pipeline:
1. **Structural verification** (`PlanVerifier`) — checks graph shape: empty-graph and cycles are hard failures; disconnected components are warnings.
2. **Symbolic verification** (`PDDLSymbolicVerifier`) — delegates PDDL executability checking to the external VAL validator.
3. **Domain-specific validation** (optional) — e.g., `BlocksworldPhysicsValidator` simulates action effects and checks additional physical constraints.

`IntegratedVerifier` composes all three layers into a single verdict and produces repair-oriented feedback for the planner.

> **Source:** substrate_packet §2 (claims 6–8), §4.

### C3 — Verifier-guided repair loop

The framework closes a plan–verify–repair cycle:
- After layered verification, `IntegratedVerifier.build_planner_feedback()` condenses failed layers and key errors into structured repair prompts.
- The generic PDDL runner (`run_generic_pddl_eval.py`, current mainline runtime) orchestrates iterative re-generation with VAL-guided feedback.
- On TravelPlanner, a separate repair pipeline (`bdi-repair`) applies non-oracle local repair at test time and oracle-guided repair during validation evaluation.

> **Source:** substrate_packet §4 (claims on `forward()` and `IntegratedVerifier`), planbench_packet §2 (claim 2), travelplanner_packet §2 (claims 2–3).

### C4 — Two complementary evidence surfaces

The substrate's generality is validated across two qualitatively different planning domains:

#### C4a — Formal PDDL planning (PlanBench-style, current-mainline snapshot)

| Domain | baseline | bdi | bdi-repair |
| --- | ---: | ---: | ---: |
| blocksworld | 1103/1103 (100.0%) | 1103/1103 (100.0%) | 1103/1103 (100.0%) |
| logistics | 0/572 (0.0%) | 557/572 (97.4%) | 572/572 (100.0%) |
| depots | 498/501 (99.4%) | 478/501 (95.4%) | 501/501 (100.0%) |
| obfuscated_deceptive_logistics | 546/572 (95.5%) | 546/572 (95.5%) | 572/572 (100.0%) |
| obfuscated_randomized_logistics | 547/572 (95.6%) | 536/572 (93.7%) | 572/572 (100.0%) |

**Headline:** The verify–repair loop recovers logistics from complete baseline collapse (0 %) to 100 %, and all five domains reach 100 % under bdi-repair.

> **Provenance:** current-mainline snapshot from `README.md`, `docs/BENCHMARKS.md`, `RESULTS_PROVENANCE.md` (planbench_packet §4). These are **not** the frozen paper snapshot numbers from `artifacts/paper_eval_20260213/`.

#### C4b — Real-constraint planning (TravelPlanner)

| Surface | Repair visibility | baseline | bdi (v3) | bdi-repair |
| --- | --- | ---: | ---: | ---: |
| Validation oracle (N=180) | + evaluator-guided oracle repair | 0.211 | 0.578 | 0.706 |
| Validation-as-test (N=180) | non-oracle only | 0.211 | 0.578 | 0.606 |
| Official test (N=1000) | non-oracle only | 0.382 | 0.609 | 0.647 |

**Deployment-aligned headline:** Final Pass Rate 38.2 % → 64.7 % on the official 1000-query test leaderboard (non-oracle).
**Oracle upper bound (diagnostic):** 70.6 % under validation oracle evaluation.

> **Provenance:** travelplanner_packet §4. Oracle validation numbers are evaluator-feedback-dependent and must not be presented as deployment/test-time claims.

---

## Narrative defaults (from drafting plan §4)

1. **Abstract:** Center on shared substrate + layered verification contribution, with summary evidence across both PDDL and TravelPlanner surfaces. Foreground deployment-aligned numbers.
2. **Methods:** Foreground the shared substrate and layered verification stack. No benchmark headline numbers in this section.
3. **PDDL results:** Foreground the logistics recovery story. Use five-domain table as compact support.
4. **TravelPlanner results:** Foreground deployment-aligned claims (validation-as-test + official test). Oracle validation as diagnostic upper bound.
5. **SWE-bench:** Appendix only — does not appear in abstract or contribution spine.

---

## Provenance compliance checklist for this document

- [x] PDDL numbers sourced from planbench_packet §4 (current-mainline snapshot), explicitly labeled.
- [x] TravelPlanner numbers sourced from travelplanner_packet §4, with three surfaces explicitly separated.
- [x] Frozen paper snapshot not mixed with current-mainline numbers.
- [x] Oracle validation (`0.706`) explicitly marked as evaluator-feedback-dependent diagnostic.
- [x] Deployment-aligned headline uses official test (`0.647`) and validation-as-test (`0.606`), not oracle.
- [x] `run_generic_pddl_eval.py` referenced as current mainline runtime (not legacy).
- [x] SWE-bench absent from abstract and contribution spine (appendix-only rule).
- [x] Terminology uses locked terms: shared substrate, layered verification, current mainline runtime, oracle repair, non-oracle local repair.
