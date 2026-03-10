# Provenance & Figure Policy Note — Manuscript Drafting Stage

> **Purpose:** Machine-friendly quick-reference for all provenance constraints that govern the PNSV manuscript. Every prose-generation agent or human author must check these rules before writing any claim, table, or figure caption.

---

## 1. Frozen-vs-Current PlanBench Boundary

| Surface | Approved source | Scope |
| --- | --- | --- |
| **Frozen paper snapshot** | `artifacts/paper_eval_20260213/MANIFEST.json:94-125` + verifier `scripts/evaluation/verify_paper_eval_snapshot.py` | Canonical for all paper PlanBench headline claims. Uses **checkpoint-based** denominators (200/570/500 → 1270 total). |
| **Current mainline snapshot** | `README.md:158-177`, `docs/BENCHMARKS.md:40-63`, `RESULTS_PROVENANCE.md:14-23` | Repository status reporting only. Source artifacts under `runs/planbench/` (mutable, dated 2026-03-07). Five domains, different denominators. |

### Rules

1. **Never mix** frozen-paper and current-mainline numbers in the same unlabeled table or prose claim.
2. If both surfaces appear in one section, they must occupy **separate, explicitly labeled tables** (e.g., "Frozen Paper Snapshot" vs "Current Mainline Snapshot").
3. Paper denominators are checkpoint-based (logistics 570, depots 500), **not** raw upstream result-dump row counts (572, 501). The delta is documented in `MANIFEST.json:127-145`.

---

## 2. PDDL Runner Boundary

| Runner | Status | Citation rule |
| --- | --- | --- |
| `scripts/evaluation/run_generic_pddl_eval.py` | **Current mainline runtime** | Canonical for all PlanBench-style evaluation. |
| `scripts/evaluation/run_verification_only.py` | **Active supporting harness** | Cite only as diagnostic/analysis tool (generation + structural + symbolic checks, agreement stats), not as canonical runtime. Covers 3 domains only. |
| `scripts/evaluation/_legacy/run_planbench_full.py` | **Legacy / historical only** | Must not be described as current-mainline runtime under any circumstances. |

---

## 3. TravelPlanner Field Boundary

### Three evaluation surfaces (must be named explicitly)

1. **Oracle validation** — evaluator feedback available during repair (`summary` field in `bdi-repair` results).
2. **Validation-as-test (non-oracle)** — no oracle feedback during repair (`validation_as_test_summary` field in `bdi-repair` results).
3. **Official test submission** — shared non-oracle sole-planning path via `generate_submission.py`.

### Rules

1. **`summary` ≠ `validation_as_test_summary`**. The `summary` field from a `bdi-repair` results file reflects the post-oracle evaluation path. Reading only `summary` silently imports oracle repair gains.
2. Oracle validation numbers (e.g., final pass rate 0.706) must be **explicitly labeled as diagnostic upper bound / ceiling**, not deployment-aligned performance.
3. Official test submission results (baseline 0.382 → bdi 0.609 → bdi-repair 0.647) are the **primary deployment-aligned claims**.
4. Validation-as-test results (baseline 0.211 → bdi 0.578 → bdi-repair 0.606) are acceptable for non-oracle comparison but must be labeled as such.

### Source anchors

- `src/bdi_llm/travelplanner/runner.py:174-209` — per-instance metric separation.
- `src/bdi_llm/travelplanner/runner.py:222-235` and `:360-377` — checkpoint/results payloads emit both `summary` and `validation_as_test_summary`.

---

## 4. Figure-Script Policy

### General rule

Figure scripts under `scripts/paper/` are **not standalone trusted evidence**. They must be validated for:
- Correct **path resolution** (all scripts compute `ROOT = Path(__file__).resolve().parent.parent` → resolves to `scripts/`, not repo root).
- Correct **data source scope** (checkpoint-based frozen data vs approximate/estimated inputs).

### Per-figure risks

| Figure | Risk | Policy |
| --- | --- | --- |
| **Figure 2** (main results) | GPT-4 baseline bars use **approximate values** from a cited external table (`baseline_acc = [35.0, 5.0, 5.0]`), not exact repo-local evidence (`gen_fig2_main_results.py:37-38`). | Caption must label baseline bars as "approximate reproductions from [cited source]". Do not present as exact re-measurements. |
| **Figure 3** (complexity) | Data source is exact (checkpoint-based), but path resolution is likely wrong. | Verify script output path before using generated artifact. |
| **Figure 4** (VAL repair) | Data source is exact (checkpoint-based), but path resolution is likely wrong. | Verify script output path before using generated artifact. |
| **Figure 5** (logistics improvement) | Final/pre-repair stages are data-backed; intermediate stages (45.0%, 70.0%) are **narrative estimates** (`gen_fig5_logistics_improvement.py:52-60`). | Label intermediate bars as estimates in caption. Do not present as measured exact values. |

### Snapshot verifier

`scripts/evaluation/verify_paper_eval_snapshot.py:76-80` has the same `ROOT` resolution risk — default snapshot directory may resolve under `scripts/artifacts/...` instead of repo-root `artifacts/...`. The verifier logic is sound; the default path may be wrong.

---

## 5. SWE-bench Boundary

- SWE-bench content is **appendix-only**.
- It must not displace nor be intermixed with the main substrate / PDDL / TravelPlanner narrative.
- No SWE-bench numbers should appear in the main results sections (§4, §5).

---

## 6. Terminology Locks

The following terms are locked across all manuscript sections for consistency:

| Term | Meaning |
| --- | --- |
| current mainline runtime | `run_generic_pddl_eval.py` |
| frozen paper snapshot | `artifacts/paper_eval_20260213/` checkpoint-based evidence |
| layered verification | structural → symbolic → domain-specific verification chain |
| verifier-guided repair loop | VAL feedback → `build_planner_feedback()` → `repair_from_val_errors()` iterative cycle |
| oracle validation | TravelPlanner evaluation with evaluator feedback (post-oracle path) |
| validation-as-test | TravelPlanner evaluation without oracle feedback (pre-oracle / test-style path) |

---

## 7. Claim Audit Checklist (from `claim_audit_checklist.md`)

### Source-of-truth checks
- [ ] Main-text PlanBench claims do not mix frozen snapshot numbers with current-mainline repository numbers.
- [ ] Current-mainline reporting points to `README.md`, `docs/BENCHMARKS.md`, `RESULTS_PROVENANCE.md`.
- [ ] Frozen paper PlanBench evidence points to `artifacts/paper_eval_20260213/MANIFEST.json` and snapshot verifier.
- [ ] Checkpoint-based frozen denominators are distinct from upstream raw-result row counts.

### Runtime-boundary checks
- [ ] `run_generic_pddl_eval.py` is described as current-mainline runtime.
- [ ] `run_verification_only.py` is described only as supporting verification harness.
- [ ] `_legacy/run_planbench_full.py` is not described as current-mainline runtime.

### TravelPlanner boundary checks
- [ ] Validation oracle, validation-as-test, and official test submission are distinct surfaces.
- [ ] Oracle repair is only described inside validation evaluation after evaluator feedback.
- [ ] Official test submission is described as shared non-oracle path.
- [ ] `summary` and `validation_as_test_summary` are not collapsed into one field source.

### Figure / tooling checks
- [ ] Figure 2 approximate external baseline risk is explicitly noted.
- [ ] Figure 5 intermediate estimated-stage risk is explicitly noted.
- [ ] Figure scripts are not treated as standalone trusted evidence without path-resolution checks.
- [ ] Snapshot verifier path-resolution risk is explicitly noted.

### Narrative scope checks
- [ ] SWE-bench remains appendix-only and does not displace the main narrative.
- [ ] Claim ledger terminology locks are respected.

> **Usage:** Before finalizing any manuscript section, run through all items above and verify each checkbox. Unchecked items indicate a provenance violation that must be resolved before submission.
