# Results Provenance

This file documents the exact source files for every benchmark number reported in README.md.
If you regenerate results, update this file to keep the README traceable.

---

## PlanBench (PDDL)

**Source directory**: `runs/planbench/`

Each domain has `baseline/`, `bdi/`, `repair/` subdirectories containing checkpoint JSON files.

| Domain | Source Path | baseline | bdi | bdi-repair |
| --- | --- | --- | --- | --- |
| `blocksworld` | `runs/planbench/blocksworld/{baseline,bdi,repair}/` | 1103/1103 (100.0%) | 1103/1103 (100.0%) | 1103/1103 (100.0%) |
| `logistics` | `runs/planbench/logistics/{baseline,bdi,repair}/` | 0/572 (0.0%) | 557/572 (97.4%) | 572/572 (100.0%) |
| `depots` | `runs/planbench/depots/{baseline,bdi,repair}/` | 498/501 (99.4%) | 478/501 (95.4%) | 501/501 (100.0%) |
| `obfuscated_deceptive_logistics` | `runs/planbench/obfuscated_deceptive_logistics/{baseline,bdi,repair}/` | 546/572 (95.5%) | 546/572 (95.5%) | 572/572 (100.0%) |
| `obfuscated_randomized_logistics` | `runs/planbench/obfuscated_randomized_logistics/{baseline,bdi,repair}/` | 547/572 (95.6%) | 536/572 (93.7%) | 572/572 (100.0%) |

**Config**: CPA OpenAI-compatible proxy, `gpt-5(low)`, `workers=500`
**Date**: 2026-03-07

---

## TravelPlanner (Official Leaderboard, Current Release Submission)

**Source file**: `runs/travelplanner_release_matrix/test_submit/leaderboard_results.json`
**Submission files**: `runs/travelplanner_release_matrix/test_submit/test_soleplanning_{baseline,bdi,bdi-repair}.jsonl`
**Leaderboard**: https://huggingface.co/spaces/osunlp/TravelPlannerLeaderboard
**Split**: test (1000 queries), sole-planning mode
**Submitted via**: `gradio_client` API (`scripts/evaluation/submit_to_leaderboard.py`)

| Metric | baseline | bdi | bdi-repair |
| --- | --- | --- | --- |
| Delivery Rate | 1.000 | 1.000 | 1.000 |
| Commonsense Constraint Micro Pass Rate | 0.9435 | 0.972875 | 0.97725 |
| Commonsense Constraint Macro Pass Rate | 0.596 | 0.804 | 0.837 |
| Hard Constraint Micro Pass Rate | 0.8135371179039301 | 0.8441048034934497 | 0.848471615720524 |
| Hard Constraint Macro Pass Rate | 0.641 | 0.724 | 0.736 |
| Final Pass Rate | 0.382 | 0.609 | 0.647 |

**Config**: DashScope `qwq-plus`, sole-planning, 1000 test queries
**Date**: 2026-03-09

### Historical pre-convergence submission snapshot

**Source file**: `runs/tp_test_submit/leaderboard_results.json`
**Submission files**: `runs/tp_test_submit/test_soleplanning_{baseline,bdi,bdi-repair}.jsonl`

| Metric | baseline | bdi | bdi-repair |
| --- | --- | --- | --- |
| Delivery Rate | 1.000 | 1.000 | 1.000 |
| Commonsense Constraint Micro Pass Rate | 0.876 | 0.890 | 0.761 |
| Commonsense Constraint Macro Pass Rate | 0.349 | 0.375 | 0.020 |
| Hard Constraint Micro Pass Rate | 0.801 | 0.781 | 0.303 |
| Hard Constraint Macro Pass Rate | 0.623 | 0.598 | 0.213 |
| Final Pass Rate | 0.193 | 0.219 | 0.007 |

**Date**: 2026-03-08

---

## TravelPlanner (Validation Set, Converged Release Candidate)

### Current release defaults

- `baseline`: unchanged
- `bdi`: `v3`
- `bdi-repair`: `bdi v3` generator + Stage 3 `repair v4` reviewer / confidence / patch-scope / acceptance-gate logic
- `bdi v4`: retained as an experimental candidate only, not the default

### Source files

| Metric group | Source Path |
| --- | --- |
| `baseline` | `runs/travelplanner_generalization_val_v2/validation/baseline/results_travelplanner_validation_baseline_20260308_130223.json` |
| `bdi (v3)` | `runs/travelplanner_stage2_val_v3/validation/bdi/results_travelplanner_validation_bdi_20260308_174302.json` |
| `bdi-repair (v4 reviewer, oracle)` | `runs/travelplanner_stage3_val_v4/validation/bdi-repair/results_travelplanner_validation_bdi-repair_20260308_182534.json` |
| `bdi-repair (v4 reviewer, validation-as-test)` | `runs/travelplanner_stage3_val_v4/validation/bdi-repair/results_travelplanner_validation_bdi-repair_20260308_182534.json` |

### Validation (oracle evaluation)

| Metric | `baseline` | `bdi (v3)` | `bdi-repair (v4 reviewer)` |
| --- | --- | --- | --- |
| Delivery Rate | 1.000 | 1.000 | 1.000 |
| Commonsense Pass Rate | 0.378 | 0.811 | 0.839 |
| Hard Constraint Pass Rate | 0.594 | 0.683 | 0.794 |
| Final Pass Rate | 0.211 (38/180) | 0.578 (104/180) | 0.706 (127/180) |

### Validation-as-test (non-oracle path)

| Metric | `baseline` | `bdi (v3)` | `bdi-repair (v4 reviewer)` |
| --- | --- | --- | --- |
| Delivery Rate | 1.000 | 1.000 | 1.000 |
| Commonsense Pass Rate | 0.378 | 0.811 | 0.761 |
| Hard Constraint Pass Rate | 0.594 | 0.683 | 0.711 |
| Final Pass Rate | 0.211 (38/180) | 0.578 (104/180) | 0.606 (109/180) |

### Rejected experimental candidate

| Candidate | Source Path | Final Pass Rate |
| --- | --- | --- |
| `bdi v4` | `runs/travelplanner_stage3_val_v4/validation/bdi/results_travelplanner_validation_bdi_20260308_182431.json` | 0.544 (98/180) |

**Reason for rejection**: `bdi v4` regressed relative to `bdi v3` on full validation despite the new grounded two-stage generation design.

---

## TravelPlanner (Validation Set, Historical Snapshot)

**Source**: OCI server local evaluation using official TravelPlanner evaluator
**Split**: validation (180 queries), sole-planning mode
**Evaluator**: `workspaces/TravelPlanner_official/tools/evaluation/eval.py`

| Metric | baseline | bdi | bdi-repair |
| --- | --- | --- | --- |
| Delivery Rate | 1.000 | 1.000 | 1.000 |
| Commonsense Pass Rate | 0.344 | 0.417 | 0.650 |
| Hard Constraint Pass Rate | 0.589 | 0.611 | 0.672 |
| Final Pass Rate | 0.183 (33/180) | 0.261 (47/180) | 0.439 (79/180) |

**Config**: DashScope `qwq-plus`, sole-planning, 180 validation queries
**Date**: 2026-03-07

> **Historical note**: These numbers predate the current converged release candidate. They remain useful for tracking the old failure mode where validation repair gains did not transfer to the non-oracle test-style path.
