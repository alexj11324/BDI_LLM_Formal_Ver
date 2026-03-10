# Manuscript Drafting Plan

> Generated from the 5 pre-writing packets and 4 lead artifacts.
> This document establishes the dependency order, provenance constraints, and section-to-packet mapping for all subsequent prose-generation tasks.

---

## 1. Drafting dependency graph

The prose-generation tasks must proceed in the following order due to data and narrative dependencies:

```
Task 2: Abstract + Contribution Spine
    ├── depends on: claim_ledger, integrated_outline, substrate_packet
    └── unblocks: all subsequent tasks (sets thesis vocabulary)

Task 3: Methods Skeleton
    ├── depends on: substrate_packet, docs/FUNCTIONAL_FLOW.md, src/bdi_llm/ core code
    └── unblocks: result sections (defines method vocabulary)

Task 4: PDDL Results Skeleton          Task 5: TravelPlanner Results Skeleton
    ├── depends on: planbench_packet        ├── depends on: travelplanner_packet
    ├── depends on: provenance_packet       ├── depends on: provenance_packet
    └── independent of Task 5               └── independent of Task 4

Task 6: Provenance & Figure Policy Note
    ├── depends on: provenance_packet, claim_audit_checklist
    └── post-hoc: machine-friendly reference for future editing passes

Task 7: Final Verification
    └── depends on: all of Tasks 1–6 completed
```

**Parallel opportunities:** Tasks 4 and 5 are independent of each other and may be written concurrently once Tasks 2 and 3 are complete.

---

## 2. Section → packet mapping

| Manuscript section | Primary input packet(s) | Secondary references |
|---|---|---|
| Abstract + contribution spine | claim_ledger, integrated_outline, substrate_packet | All packets for numeric scope |
| Methods / shared substrate | substrate_packet | `docs/FUNCTIONAL_FLOW.md`, `src/bdi_llm/` |
| PDDL / PlanBench results | planbench_packet, provenance_packet | `RESULTS_PROVENANCE.md`, frozen snapshot |
| TravelPlanner results | travelplanner_packet, provenance_packet | `RESULTS_PROVENANCE.md`, `README.md` |
| Provenance policy note | provenance_packet, claim_audit_checklist | Figure scripts under `scripts/paper/` |
| Appendix: SWE-bench | swebench_appendix_packet | `docs/BENCHMARKS.md` |

---

## 3. Provenance constraints (must be preserved in all drafting tasks)

### 3.1 Frozen-vs-current PlanBench boundary

| Evidence surface | Approved source | Scope |
|---|---|---|
| **Paper PlanBench numbers** | `artifacts/paper_eval_20260213/MANIFEST.json` (checkpoint-based counts) | Frozen paper claims only |
| **Current mainline snapshot** | `README.md`, `docs/BENCHMARKS.md`, `RESULTS_PROVENANCE.md`, `runs/planbench/` | Repository status reporting |

**Rule:** Never mix these two surfaces in one unlabeled table or prose claim. If both appear, each must be explicitly scoped.

### 3.2 TravelPlanner field-boundary rule

| Field | Meaning | When to cite |
|---|---|---|
| `summary` (from `bdi-repair` result files) | Post-oracle evaluation, includes evaluator-guided repair | Oracle validation claims only |
| `validation_as_test_summary` | Non-oracle sole-planning path, no evaluator feedback | Deployment-aligned / test-style claims |

**Rule:** Never collapse these into a single "validation result." Always name the field source.

### 3.3 PDDL runner boundary

| Script | Role | Citation rule |
|---|---|---|
| `scripts/evaluation/run_generic_pddl_eval.py` | Current mainline runtime | May describe as "our PDDL evaluation pipeline" |
| `scripts/evaluation/run_verification_only.py` | Supporting verification harness | Describe as secondary analysis tool only |
| `scripts/evaluation/_legacy/run_planbench_full.py` | Legacy, archival | Never describe as current runtime |

### 3.4 Figure-script provenance caution

- Figure 2 baseline bars are approximate values from external cited paper table — not repo-local exact evidence.
- Figure 5 intermediate stages are narrative estimates, not measured values.
- All figure scripts likely have a `ROOT` path-resolution bug (`parent.parent` → `scripts/` not repo root); do not treat script-generated artifacts as authoritative without path verification.

---

## 4. Narrative defaults (from dry_run_summary and claim_ledger)

1. **Methods:** Foreground the shared substrate and layered verification stack. Do not include benchmark headline numbers in this section.
2. **PDDL results:** Foreground the logistics recovery story (`0/572 → 557/572 → 572/572`). Use the five-domain current-mainline table as compact supporting evidence. Keep frozen paper counts as the canonical paper evidence surface.
3. **TravelPlanner results:** Foreground deployment-aligned claims (`validation-as-test 0.606`, official test `0.647`). Keep oracle validation (`0.706`) as diagnostic upper-bound.
4. **Abstract:** Center on shared substrate + layered verification contribution, with summary evidence across both PDDL and TravelPlanner surfaces.
5. **SWE-bench:** Appendix only. Must not displace any main narrative section.

---

## 5. Terminology locks (from claim_ledger)

All drafting tasks must use consistent terminology:

- **shared substrate** — the reusable planning/verification core
- **layered verification** — structural → symbolic → domain-specific
- **current mainline runtime** — the active, non-legacy evaluation surface
- **generic PDDL / PlanBench-style evaluation** — the primary formal evidence surface
- **TravelPlanner validation oracle** — post-evaluator-feedback evaluation
- **TravelPlanner validation-as-test** — non-oracle path aligned with test submission
- **TravelPlanner official test submission** — 1000-query blind leaderboard
- **oracle repair** — repair using evaluator feedback (validation only)
- **non-oracle local repair** — repair without evaluator feedback (deployment path)
- **frozen paper snapshot** — `artifacts/paper_eval_20260213/`
- **current mainline provenance** — `README.md` / `docs/BENCHMARKS.md` / `RESULTS_PROVENANCE.md`

---

## 6. Output file inventory

Each subsequent task will produce exactly one file under `runs/spawnteam_paper/lead/`:

| Task | Output file |
|---|---|
| Task 1 (this) | `manuscript_drafting_plan.md` |
| Task 2 | `abstract_contribution_spine.md` |
| Task 3 | `methods_skeleton.md` |
| Task 4 | `pddl_results_skeleton.md` |
| Task 5 | `travelplanner_results_skeleton.md` |
| Task 6 | `provenance_policy_note.md` |
| Task 7 | (verification report — inline in progress.txt) |

---

## 7. Claim audit integration

Before Task 7, all drafted sections must pass the checks in `claim_audit_checklist.md`:

- [ ] Source-of-truth checks (frozen vs current boundary)
- [ ] Runtime-boundary checks (generic runner vs verification harness vs legacy)
- [ ] TravelPlanner boundary checks (oracle vs non-oracle vs test)
- [ ] Figure / tooling checks (approximate baselines, path bugs)
- [ ] Lead synthesis checks (narrative scope, SWE-bench containment)
