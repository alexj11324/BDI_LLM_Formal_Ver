# TravelPlanner Results Section — Skeleton Draft

> **Provenance note:** All numbers in this section are sourced from the TravelPlanner packet (travelplanner_packet §4) and the provenance packet (provenance_packet §2, §5).
> Three evaluation surfaces are maintained as **explicitly separate** throughout:
> - **Validation oracle (N=180)** — post-evaluator-feedback oracle repair; numbers from `summary` field.
> - **Validation-as-test (N=180)** — non-oracle sole-planning path; numbers from `validation_as_test_summary` field.
> - **Official test submission (N=1000)** — non-oracle sole-planning path; blind leaderboard evaluation.
>
> These three surfaces must never be collapsed into a single "TravelPlanner result."
> Oracle validation is a **diagnostic upper bound**, not a deployment claim.

---

## 5. Real-Constraint Results: TravelPlanner

TravelPlanner evaluates multi-day travel itinerary generation, requiring plans that satisfy commonsense constraints (reasonable activity timing, plausible travel logistics), hard constraints (budget limits, transportation availability, accommodation capacity), and delivery completeness. Unlike the PDDL evidence surface (§4), TravelPlanner operates through a **separate non-PDDL runtime** with its own itinerary-shaped pipeline; it does not use the `BDIPlan` graph representation or the VAL symbolic verifier.

We evaluate three experimental stages at the itinerary level:
- **baseline** — direct LLM generation with no BDI substrate.
- **bdi (v3)** — generation through the BDI planner with domain-context injection and structural planning prompts.
- **bdi-repair** — the converged release path combining the `bdi v3` generator with the Stage 3 repair stack.

> **Release configuration note:** `bdi-repair` uses the `bdi v3` generator; `bdi v4` was evaluated as an experimental candidate but rejected for the release path because it regressed versus `bdi v3` on full validation.
>
> **Source:** travelplanner_packet §2 (claim 4), `RESULTS_PROVENANCE.md:67-72`.

### 5.1 Evaluation Protocol and Oracle/Non-Oracle Distinction

A critical design feature of the TravelPlanner evaluation is the separation between **oracle repair** and **non-oracle local repair**:

- **Oracle repair** is available only during **validation evaluation**. After the evaluator scores an initial plan, evaluator feedback (constraint violation details) is used to guide a repair iteration. This produces the `summary` field in `bdi-repair` result artifacts.
- **Non-oracle local repair** is the deployment-aligned path: the system generates and locally refines plans without access to evaluator feedback. This produces the `validation_as_test_summary` field in `bdi-repair` result artifacts and is the same code path used for the official test submission (`generate_submission(...)`).

> **Field-boundary rule (from provenance_packet §2, rule 6; travelplanner_packet §2, claims 2–3):**
> - `summary` → oracle validation claims only (post-evaluator-feedback).
> - `validation_as_test_summary` → non-oracle / deployment-aligned claims.
> - These two fields must never be collapsed into a single validation number for `bdi-repair`.
> - Reading only `summary` from a `bdi-repair` file would overstate deployment-aligned performance.

For `baseline` and `bdi` modes, no oracle repair is applied; their `summary` and `validation_as_test_summary` are identical.

> **Source:** `src/bdi_llm/travelplanner/runner.py:167-209` (oracle repair path), `runner.py:366-377` (dual-field emission), travelplanner_packet §2 (claims 2–3), §5 (caveats 1–3).

### 5.2 Main Results: Deployment-Aligned Evidence

The central deployment-aligned claims come from the **validation-as-test** and **official test submission** surfaces, both of which use the shared non-oracle sole-planning path.

#### 5.2.1 Official Test Submission (N=1000, Leaderboard)

| Metric | baseline | bdi (v3) | bdi-repair |
| --- | ---: | ---: | ---: |
| Delivery Rate | 1.000 | 1.000 | 1.000 |
| Commonsense Micro | 0.9435 | 0.972875 | 0.97725 |
| Commonsense Macro | 0.596 | 0.804 | 0.837 |
| Hard Constraint Micro | 0.814 | 0.844 | 0.848 |
| Hard Constraint Macro | 0.641 | 0.724 | 0.736 |
| **Final Pass Rate** | **0.382** | **0.609** | **0.647** |

> **Provenance:** `RESULTS_PROVENANCE.md:27-45`, `runs/travelplanner_release_matrix/test_submit/leaderboard_results.json`. Non-oracle sole-planning path; the test submission script reuses `generate_submission(...)` and does not apply oracle repair.
>
> **Source:** travelplanner_packet §4C, §2 (claim 5), §5 (caveat 2).

**Headline result:** `bdi-repair` achieves **Final Pass Rate 0.647** on the official 1000-query test leaderboard, up from 0.382 (baseline) — a **69.4% relative improvement**. The BDI substrate alone (`bdi v3`) accounts for the majority of the lift (0.382 → 0.609), and the repair stack provides incremental gains (0.609 → 0.647).

#### 5.2.2 Validation-as-Test (N=180, Non-Oracle)

| Metric | baseline | bdi (v3) | bdi-repair |
| --- | ---: | ---: | ---: |
| Delivery Rate | 1.000 | 1.000 | 1.000 |
| Commonsense Pass Rate | 0.378 | 0.811 | 0.761 |
| Hard Constraint Pass Rate | 0.594 | 0.683 | 0.711 |
| **Final Pass Rate** | **0.211** (38/180) | **0.578** (104/180) | **0.606** (109/180) |

> **Provenance:** travelplanner_packet §4B (validation-as-test table). Numbers from `validation_as_test_summary` field in `bdi-repair` result artifacts. **Not** the oracle `summary` field.
>
> **Source:** `RESULTS_PROVENANCE.md:92-99`.

**Observation:** On the validation split under the non-oracle deployment path, `bdi-repair` reaches **Final Pass Rate 0.606** (109/180) — consistent with the official test trajectory (0.647). The validation-as-test numbers are the proper deployment-aligned validation counterpart to the leaderboard submission.

### 5.3 Oracle Validation: Diagnostic Upper Bound

Oracle validation represents the **ceiling performance** achievable when evaluator feedback is available for repair. This surface is reported as a **diagnostic upper bound**, not as a deployment or test-time claim.

| Metric | baseline | bdi (v3) | bdi-repair |
| --- | ---: | ---: | ---: |
| Delivery Rate | 1.000 | 1.000 | 1.000 |
| Commonsense Pass Rate | 0.378 | 0.811 | 0.917 |
| Hard Constraint Pass Rate | 0.594 | 0.683 | 0.794 |
| **Final Pass Rate** | **0.211** (38/180) | **0.578** (104/180) | **0.706** (127/180) |

> **Provenance:** travelplanner_packet §4B (validation oracle table). Numbers from `summary` field in `bdi-repair` result artifacts. This is the **oracle evaluation path** with evaluator-guided repair — these numbers must not be attributed to the deployment/test-time configuration.
>
> **Source:** `RESULTS_PROVENANCE.md:83-90`.

**Oracle–deployment gap analysis:** The gap between oracle (0.706) and non-oracle (0.606) validation demonstrates that evaluator feedback provides a meaningful additional repair signal. The ~10 percentage-point difference quantifies the headroom available if a deployment-time evaluator were available — indicating that the current non-oracle repair extracts most but not all of the achievable gains.

### 5.4 Cross-Surface Comparison

The following summary table consolidates the three surfaces for direct comparison. Each row represents a distinct evaluation configuration with its own repair-visibility semantics:

| Surface | Repair visibility | baseline | bdi (v3) | bdi-repair |
| --- | --- | ---: | ---: | ---: |
| Validation oracle (N=180) | + evaluator-guided oracle repair | 0.211 | 0.578 | **0.706** |
| Validation-as-test (N=180) | non-oracle only | 0.211 | 0.578 | **0.606** |
| Official test (N=1000) | non-oracle only | 0.382 | 0.609 | **0.647** |

> **Provenance:** travelplanner_packet §4A (direct-quote release table). Each row uses explicitly distinct evidence sources.

**Key patterns:**

1. **Consistent lift across all surfaces.** `bdi-repair` improves over baseline on all three surfaces: +49.5 pp (oracle validation), +39.5 pp (validation-as-test), +26.5 pp (official test).
2. **BDI substrate drives the majority of gains.** On the official test, `bdi v3` alone lifts Final Pass Rate from 0.382 to 0.609 (+22.7 pp); the repair stack adds 0.609 → 0.647 (+3.8 pp).
3. **Test–validation alignment.** The non-oracle validation-as-test number (0.606) and the official test number (0.647) are broadly consistent, suggesting that validation results under the shared non-oracle path are predictive of test performance.
4. **Oracle gap is concentrated in `bdi-repair`.** For `baseline` and `bdi`, oracle and non-oracle numbers are identical (because no oracle repair is applied). The 0.706–0.606 gap under `bdi-repair` isolates the incremental value of evaluator feedback.

### 5.5 Metric Decomposition

Beyond Final Pass Rate, TravelPlanner evaluates plans along three constraint axes. The metric relationship across evaluation surfaces reveals where the BDI substrate and repair stack have their effects:

**Commonsense constraints.** The BDI substrate provides the largest commonsense lift: baseline 0.378 → bdi 0.811 on validation oracle (+43.3 pp). Oracle repair further improves to 0.917, while the non-oracle deployment path settles at 0.761 — indicating that oracle feedback disproportionately helps commonsense constraint satisfaction.

**Hard constraints.** Hard constraint pass rates improve more modestly: baseline 0.594 → bdi 0.683 → bdi-repair 0.794 (oracle) / 0.711 (non-oracle). The tighter gains suggest that hard constraints (budget, capacity) are partially captured by structured planning but are harder to fully repair without explicit constraint check feedback.

**Delivery rate.** All configurations achieve 1.000 delivery rate, indicating that plan generation consistently produces complete itineraries. The filtering occurs at the constraint satisfaction level, not at the plan-completion level.

> **Metric naming note (from travelplanner_packet §5, caveat 6):** Validation tables use aggregate pass rates (Commonsense Pass Rate, Hard Constraint Pass Rate); official leaderboard tables use micro/macro variants. These are related but not interchangeable — micro metrics weight equally across constraint instances, while macro metrics weight equally across queries.

### 5.6 Narrative Position

TravelPlanner serves as the paper's **real-constraint evidence surface** (complementing the formal PDDL evidence in §4). The key narrative contributions are:

1. **Substrate generality.** The same shared substrate design (§3) — task normalization, domain specification, structured generation, verification, repair — extends to a non-PDDL domain with qualitatively different constraint types, demonstrating that PNSV is not limited to formal symbolic planning.

2. **Deployment-aligned evaluation.** By maintaining the oracle/non-oracle separation, the paper provides an honest assessment of what the system achieves at deployment time (0.647 official test) versus what is achievable under idealized conditions (0.706 oracle validation). This avoids the common pitfall of reporting oracle-inflated numbers as deployment performance.

3. **Complementary evidence structure.** PDDL results demonstrate the framework's ability to achieve near-perfect symbolic correctness (100% under repair); TravelPlanner results demonstrate meaningful improvement on softer, multi-dimensional constraint satisfaction where perfection is neither expected nor achieved.

---

## Provenance compliance checklist for this document

- [x] Three evaluation surfaces (validation oracle, validation-as-test, official test) presented as **explicitly separate** tables throughout.
- [x] Oracle validation (0.706) explicitly labeled as **diagnostic upper bound**, not deployment claim.
- [x] Deployment-aligned headline uses **official test (0.647)** and **validation-as-test (0.606)**, not oracle.
- [x] `summary` field cited only for oracle validation claims; `validation_as_test_summary` cited for non-oracle claims.
- [x] Official test submission described as **shared non-oracle sole-planning path** (`generate_submission(...)`); no oracle repair.
- [x] `bdi v4` acknowledged as rejected experimental candidate, not current release default.
- [x] Metric naming difference between validation (aggregate pass rates) and leaderboard (micro/macro) explicitly noted.
- [x] No PDDL/PlanBench numbers in this section (separate evidence surface).
- [x] No SWE-bench content (appendix-only rule).
- [x] No frozen paper snapshot numbers mixed with TravelPlanner results.
- [x] Terminology uses locked terms: non-oracle local repair, oracle repair, validation oracle, validation-as-test, official test submission, shared substrate, layered verification.
