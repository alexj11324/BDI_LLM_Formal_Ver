# PDDL Results Section — Skeleton Draft

> **Provenance note:** This section presents results from two explicitly separated evidence surfaces:
> - **Frozen paper snapshot** → `artifacts/paper_eval_20260213/MANIFEST.json` (checkpoint-based counts, canonical for paper claims)
> - **Current mainline snapshot** → `README.md`, `docs/BENCHMARKS.md`, `RESULTS_PROVENANCE.md`, `runs/planbench/` (repository status reporting, dated 2026-03-07)
>
> These two surfaces must never be merged into a single unlabeled table or prose claim.

---

## 4. Formal-Planning Results: Generic PDDL / PlanBench-Style Evaluation

We evaluate PNSV on five PDDL planning domains drawn from PlanBench, assessing three experimental stages:
- **baseline** — direct LLM generation with no BDI substrate, no structured verification, no repair.
- **bdi** — generation through the BDI planner with structural verification and domain-context injection, but no VAL-guided repair loop.
- **bdi-repair** — full PNSV pipeline: BDI generation + layered verification + verifier-guided iterative repair.

### 4.1 Experimental Setup

**Runtime.** All PDDL results are produced by the current mainline generic PDDL runner (`scripts/evaluation/run_generic_pddl_eval.py`), which implements the end-to-end flow described in §3.7: PDDL domain ingestion → task normalization → plan generation → serialization → structural verification → VAL symbolic verification → optional verifier-guided repair → artifact persistence.

> **Runner boundary clarification:**
> - `run_generic_pddl_eval.py` is the **current mainline runtime** and the canonical source of all PlanBench-style evaluation results.
> - `run_verification_only.py` is an **active supporting harness** for verification-focused analysis (generation + structural + symbolic checks, agreement/detection statistics) without repair. It should not be cited as the canonical generic runtime.
> - `_legacy/run_planbench_full.py` is **historical reference only** and is not part of the current evaluation surface.

**Domains.** Five domains from PlanBench:
1. **Blocksworld** — block stacking/unstacking with physical constraints.
2. **Logistics** — object transport across locations using trucks and airplanes.
3. **Depots** — combined storage/transport domain.
4. **Obfuscated Deceptive Logistics** — logistics with renamed predicates designed to mislead LLMs.
5. **Obfuscated Randomized Logistics** — logistics with randomized predicate renaming.

**Model and configuration.** CPA OpenAI-compatible proxy, `gpt-5(low)`, `workers=500`.

> **Source:** planbench_packet §4 (config note), `RESULTS_PROVENANCE.md:22-23`, `docs/BENCHMARKS.md:62-63`.

### 4.2 Main Results

#### 4.2.1 Current Mainline Snapshot *(repository status reporting)*

The following table reports the current mainline PlanBench snapshot (dated 2026-03-07) across all five domains. This is the **current mainline repository reporting surface**, not the frozen paper snapshot.

| Domain | baseline | bdi | bdi-repair |
| --- | ---: | ---: | ---: |
| blocksworld | 1103/1103 (100.0%) | 1103/1103 (100.0%) | 1103/1103 (100.0%) |
| logistics | 0/572 (0.0%) | 557/572 (97.4%) | 572/572 (100.0%) |
| depots | 498/501 (99.4%) | 478/501 (95.4%) | 501/501 (100.0%) |
| obfuscated_deceptive_logistics | 546/572 (95.5%) | 546/572 (95.5%) | 572/572 (100.0%) |
| obfuscated_randomized_logistics | 547/572 (95.6%) | 536/572 (93.7%) | 572/572 (100.0%) |

> **Provenance:** Current mainline snapshot from `README.md:167-173`, `docs/BENCHMARKS.md:52-64`, `RESULTS_PROVENANCE.md:14-23`. Source artifacts under `runs/planbench/` (mutable, dated 2026-03-07).

**Key observation:** Under the full verify–repair loop (`bdi-repair`), all five domains reach **100% success rate**. The most dramatic recovery is logistics, which goes from complete baseline collapse (0/572 = 0%) to full recovery (572/572 = 100%).

#### 4.2.2 Frozen Paper Snapshot *(canonical paper evidence)*

The frozen paper snapshot covers three core domains evaluated under `bdi-repair` with the Gemini-3-flash-preview model. These checkpoint-based counts constitute the canonical paper evidence.

| Domain | Passed | Total | Accuracy |
| --- | ---: | ---: | ---: |
| blocksworld | 200 | 200 | 100.0% |
| logistics | 568 | 570 | 99.6% |
| depots | 497 | 500 | 99.4% |
| **overall** | **1265** | **1270** | **99.6%** |

> **Provenance:** `artifacts/paper_eval_20260213/MANIFEST.json:94-125` (checkpoint-based counts). Model: `vertex_ai/gemini-3-flash-preview`.
>
> **Denominator note:** The paper uses checkpoint-based denominators (570 logistics, 500 depots) rather than raw upstream result file row counts (572, 501). The delta arises from duplicate/extra rows in the raw result dumps; see `MANIFEST.json:127-145` for explicit reconciliation.
>
> **Failed instances:** 5 total — logistics: `instance-166.pddl`, `instance-228.pddl`; depots: `instance-173.pddl`, `instance-179.pddl`, `instance-187.pddl`.

### 4.3 Logistics Recovery Story

The logistics domain provides the most informative case study for the verify–repair loop.

**The problem.** Under direct baseline prompting (no BDI substrate), the LLM produces 0/572 valid plans — a complete collapse. This is likely attributable to the logistics domain's multi-vehicle, multi-location structure, which requires coordinated loading/unloading/driving sequences that simple text prompting cannot reliably produce.

**BDI recovery.** With BDI domain-context injection and structural verification (without VAL repair), success recovers to 557/572 (97.4%). The structured domain specification (`DomainSpec.from_pddl()`) provides the LLM with explicit action schemas, typed parameters, and precondition/effect specifications that guide the generation toward executable action sequences.

**Verify–repair closure.** The remaining 15/572 failures are resolved by the verifier-guided repair loop: VAL identifies specific precondition violations and goal-reachability failures, `IntegratedVerifier.build_planner_feedback()` compresses these into repair prompts, and `BDIPlanner.repair_from_val_errors()` iteratively re-generates until all plans pass VAL validation.

> **Provenance:** Current mainline snapshot numbers. Logistics baseline: 0/572 → bdi: 557/572 → bdi-repair: 572/572 (`README.md:175-177`, planbench_packet §4).

### 4.4 Cross-Domain Analysis

Beyond logistics, the five-domain table reveals several patterns:

1. **Blocksworld** is already fully solved at baseline (1103/1103), indicating that the domain's constrained structure is well-represented in LLM pre-training data. The verify–repair loop provides no marginal lift here but does not degrade performance.

2. **Depots** shows a small BDI regression (99.4% → 95.4%) followed by full repair recovery (100%). The initial BDI dip may reflect over-constrained action ordering from the structured generation format.

3. **Obfuscated domains** test robustness to predicate renaming. Both obfuscated logistics variants start with high baseline accuracy (95.5%, 95.6%) — suggesting the LLM partially pattern-matches despite obfuscation — and the verify–repair loop closes the remaining gaps to 100%.

### 4.5 Supporting Verification Harness

`run_verification_only.py` provides additional diagnostic statistics — generation, structural verification, VAL verification, and agreement/detection rates — without invoking the repair loop. It serves as a **supporting analysis tool** that measures how often the structural and symbolic verifiers agree, how often they detect genuine failures, and the false-positive rate.

> **Scope limitation:** The verification harness currently supports only three domains (blocksworld, logistics, depots) in its CLI choices. It should not be portrayed as the full five-domain public snapshot surface.

> **Source:** planbench_packet §2 (claim 3), §3, §5 (caveat 6).

### 4.6 Figures

> **Figure caveat:** The paper includes visualization figures (Figures 2–5) generated by scripts under `scripts/paper/`. These figures present data from the **frozen paper snapshot** evidence surface.
>
> **Known risks (from provenance_packet §5):**
> - **Figure 2:** GPT-4 baseline bars use approximate values from a cited external table (`baseline_acc = [35.0, 5.0, 5.0]`), not exact repo-local evidence. If used in the manuscript, the caption must label these as approximate reproductions from the cited source.
> - **Figure 5:** Intermediate improvement stages (45.0%, 70.0%) are narrative estimates, not measured values. Only final and pre-repair stages are data-backed.
> - **Path resolution:** All figure scripts compute `ROOT = Path(__file__).resolve().parent.parent`, which resolves to `scripts/` rather than repo root. Script-generated figure artifacts should be verified for correct path resolution before use.

---

## Provenance compliance checklist for this document

- [x] Current mainline and frozen paper snapshot presented as **explicitly separate** tables with distinct provenance labels.
- [x] `run_generic_pddl_eval.py` described as current mainline runtime; `_legacy/run_planbench_full.py` not cited as current.
- [x] `run_verification_only.py` described as supporting harness, not canonical generic runtime.
- [x] Frozen paper numbers sourced from `MANIFEST.json:94-125` (checkpoint-based counts), not raw upstream result dumps.
- [x] Checkpoint-vs-upstream denominator delta explicitly noted (570 vs 572 logistics, 500 vs 501 depots).
- [x] Figure 2 approximate baseline and Figure 5 estimated intermediate stages explicitly flagged.
- [x] Figure-script path-resolution risk noted.
- [x] Current mainline config noted: CPA proxy, `gpt-5(low)`, `workers=500`.
- [x] No TravelPlanner or SWE-bench numbers in this section (separate evidence surfaces).
- [x] Terminology uses locked terms: current mainline runtime, frozen paper snapshot, layered verification, verifier-guided repair loop.
