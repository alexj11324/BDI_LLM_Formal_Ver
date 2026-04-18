# Evaluation & Benchmarks

This page is a **high-level benchmark summary** for the current mainline runtime.

For runtime architecture, execution flow, and active-vs-legacy boundaries, see [Functional Flow](FUNCTIONAL_FLOW.md).

For exact numbers, source files, and submission provenance, use:
- [README.md](../README.md) — current user-facing benchmark snapshot and TravelPlanner release notes
- [RESULTS_PROVENANCE.md](../RESULTS_PROVENANCE.md) — exact source paths for every reported benchmark number

If you are looking for older benchmark narratives or historical in-progress notes, treat them as archival unless they are explicitly linked from the two files above.

---

## Current benchmark surfaces

The active evaluation surfaces in this repository are:

1. **Generic PDDL / PlanBench-style evaluation**
   - current runner: `scripts/evaluation/run_generic_pddl_eval.py`
   - verification-only runner: `scripts/evaluation/run_verification_only.py`

2. **TravelPlanner**
   - current validation runner: `scripts/evaluation/run_travelplanner_eval.py`
   - convenience wrappers:
     - `scripts/evaluation/run_travelplanner_baseline.py`
     - `scripts/evaluation/run_travelplanner_bdi.py`
     - `scripts/evaluation/run_travelplanner_repair.py`
   - release / submission tooling:
     - `scripts/evaluation/run_travelplanner_release_matrix.py`
     - `scripts/evaluation/run_travelplanner_test_submit.py`
     - `scripts/evaluation/submit_to_leaderboard.py`

3. **SWE-bench / coding-domain evaluation**
   - batch runner: `scripts/swe_bench/run_swe_bench_batch.py`

---

## Current PlanBench snapshot

The latest mainline PlanBench snapshot reported in the repository is documented in:
- [README.md](../README.md#latest-benchmark-snapshot)
- [RESULTS_PROVENANCE.md](../RESULTS_PROVENANCE.md#planbench-pddl)

### Stage semantics

- `baseline`: strict direct action-generation baseline
- `bdi`: initial BDI checkpoint without repair
- `bdi-repair`: full verify-repair pipeline

### Latest reported numbers

| Domain | `baseline` | `bdi` | `bdi-repair` |
| --- | --- | --- | --- |
| `blocksworld` | `1103/1103 (100.0%)` | `1103/1103 (100.0%)` | `1103/1103 (100.0%)` |
| `logistics` | `0/572 (0.0%)` | `557/572 (97.4%)` | `572/572 (100.0%)` |
| `depots` | `498/501 (99.4%)` | `478/501 (95.4%)` | `501/501 (100.0%)` |
| `obfuscated_deceptive_logistics` | `546/572 (95.5%)` | `546/572 (95.5%)` | `572/572 (100.0%)` |
| `obfuscated_randomized_logistics` | `547/572 (95.6%)` | `536/572 (93.7%)` | `572/572 (100.0%)` |

Config note:
- provider path recorded in provenance: CPA OpenAI-compatible proxy, `gpt-5(low)`, `workers=500`

---

## Current TravelPlanner snapshot

The current TravelPlanner release state is documented in:
- [README.md](../README.md#travelplanner)
- [RESULTS_PROVENANCE.md](../RESULTS_PROVENANCE.md#travelplanner-official-leaderboard-current-release-submission)
- [RESULTS_PROVENANCE.md](../RESULTS_PROVENANCE.md#travelplanner-validation-set-converged-release-candidate)

### Current release defaults

- `baseline`: unchanged direct itinerary baseline
- `bdi`: `v3`
- `bdi-repair`: `bdi v3` generator + Stage 3 repair/reviewer stack
- `bdi v4`: retained as an experimental candidate, but not the default release path

### Current validation release candidate (N=180)

| Metric | `baseline` | `bdi (v3)` | `bdi-repair (v4 reviewer)` |
| --- | --- | --- | --- |
| Delivery Rate | 100.0% | 100.0% | 100.0% |
| Commonsense Pass Rate | 37.8% | 81.1% | **83.9%** |
| Hard Constraint Pass Rate | 59.4% | 68.3% | **79.4%** |
| Final Pass Rate | 21.1% (38/180) | 57.8% (104/180) | **70.6% (127/180)** |

### Current test submission (N=1000)

| Metric | `baseline` | `bdi (v3)` | `bdi-repair (v4 reviewer)` |
| --- | --- | --- | --- |
| Delivery Rate | 100.0% | 100.0% | 100.0% |
| Commonsense Micro | 94.35% | 97.29% | **97.73%** |
| Commonsense Macro | 59.6% | 80.4% | **83.7%** |
| Hard Constraint Micro | 81.35% | 84.41% | **84.85%** |
| Hard Constraint Macro | 64.1% | 72.4% | **73.6%** |
| Final Pass Rate | 38.2% | 60.9% | **64.7%** |

---

## Active benchmark commands

### Generic PDDL / PlanBench-style

```bash
# Single generic PDDL problem
python scripts/evaluation/run_generic_pddl_eval.py --domain_pddl tests/fixtures/gripper/domain.pddl --problem_pddl tests/fixtures/gripper/problem1.pddl

# Batch generic PDDL directory with VAL checking
python scripts/evaluation/run_generic_pddl_eval.py --domain_pddl tests/fixtures/gripper/domain.pddl --problem_dir tests/fixtures/gripper --execution_mode VERIFY_WITH_VAL

# Verification-only evaluation
python scripts/evaluation/run_verification_only.py --domain blocksworld --max_instances 10
```

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

### SWE-bench

```bash
python scripts/swe_bench/run_swe_bench_batch.py --limit 5 --output_dir runs/swe_bench_results
```

---
