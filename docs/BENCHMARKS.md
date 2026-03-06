# Evaluation & Benchmarks

This document tracks reproducible benchmark results and the artifact files that back them.
Use this file as the benchmark ledger. The root `README.md` explains how to run evaluations, but the concrete numbers live here.

The JSON result files under `runs/` are the source of truth. In-progress runs are recorded as checkpoint snapshots and must not be cited as final numbers.

## Benchmark Setup

- Dataset: PlanBench (Valmeekam et al., 2023)
- Domains used in this repository: Blocksworld, Logistics, Depots
- Logistics full-dataset size in this repo: 572 instances
- Logistics split:
  - `generated/`: 286 instances
  - `generated_basic/`: 286 instances
- Execution modes:
  - `BASELINE`: direct LLM-to-PDDL action generation, validated by VAL
  - `BDI`: structured BDI generation before the repair loop
  - `BDI_REPAIR`: BDI generation plus structural, symbolic, and physics verification with repair
- Primary metrics:
  - `success_count` / `success_rate`
  - `avg_generation_time`
  - repair trigger/success stats when applicable

## Latest Completed Runs

### Logistics, Full Dataset, Supplier `gpt-5.3-codex`, `BASELINE`

| Date | Domain | Mode | Total | Success | Success Rate | Avg Generation Time | Artifact |
|------|--------|------|-------|---------|--------------|---------------------|----------|
| 2026-03-05 | Logistics | `BASELINE` | 572 | 571 | 99.8% | 76.29s | `runs/planbench_supplier_gpt53_naive_logistics_20260305_211300_session/results_logistics_20260305_213728.json` |

Breakdown:

- `generated`: 286/286
- `generated_basic`: 285/286
- Single observed failure: `generated_basic/instance-40`

### Logistics, 5-Instance Generated Slice, `BASELINE`

This slice is the original 5-instance comparison set used repeatedly during the March 5 investigation:

- `instance-1`
- `instance-10`
- `instance-100`
- `instance-101`
- `instance-102`

All five are from `workspaces/planbench_data/plan-bench/instances/logistics/generated/`.

| Model | Provider | Config | Success | Success Rate | Avg Generation Time | Artifact |
|-------|----------|--------|---------|--------------|---------------------|----------|
| `qwen3.5-plus` | DashScope | `BASELINE` | 2/5 | 40.0% | 34.47s | `runs/planbench_qwen35_naive_logistics_first5_20260305/results_logistics_20260305_215233.json` |
| `gpt-5.3-codex` | local supplier | same 5 extracted from the full-dataset `BASELINE` run | 5/5 | 100.0% | 61.25s | `runs/planbench_supplier_gpt53_naive_logistics_20260305_211300_session/results_logistics_20260305_213728.json` |
| `gpt-5` | local supplier | `BASELINE`, no `reasoning_effort` | 5/5 | 100.0% | 30.48s | `runs/planbench_supplier_gpt5_noeffort_naive_logistics_first5_20260305/results_logistics_20260305_215743.json` |
| `gpt-5` | local supplier | `BASELINE`, `reasoning_effort=low` | 5/5 | 100.0% | 12.36s | `runs/planbench_supplier_gpt5_low_naive_logistics_first5_20260305/results_logistics_20260305_220401.json` |

## Dynamic Replanning Smoke Runs

### Qwen `dynamic_replanning`, Logistics Generated Slice

| Date | Slice | Initial Success | Final Success | Notes | Artifact |
|------|-------|-----------------|---------------|-------|----------|
| 2026-03-05 | first 5 generated instances | 3/5 | 5/5 | `instance-100` repaired in round 1, `instance-102` repaired in round 2 | `runs/dynamic_replanning_qwen35_parallel_20260306_rerun2/results_logistics_20260305_200554.json` |
| 2026-03-05 | first 10 generated instances | 4/10 | 8/10 | `instance-102` and `instance-107` hit per-instance timeout | `runs/dynamic_replanning_qwen35_parallel_20260306_rerun10/results_logistics_20260305_202418.json` |

This pair of runs is important for interpretation:

- `qwen3.5-plus` is weak on the `BASELINE` condition for the 5-instance slice: 2/5
- the same model reaches 5/5 after the repair pipeline on that same slice
- this means the repair stack is materially helping Qwen rather than adding only overhead

## In-Progress Runs

### Logistics, Full Dataset, Supplier `gpt-5.3-codex`, `BDI_REPAIR`

Checkpoint snapshot from the active March 5 run:

| Snapshot Date | Domain | Mode | Completed So Far | Success So Far | Failure So Far | Rate Over Completed So Far | Artifact |
|---------------|--------|------|------------------|----------------|----------------|----------------------------|----------|
| 2026-03-05 | Logistics | `BDI_REPAIR` | 379 | 372 | 7 | 98.2% | `runs/planbench_supplier_gpt53_full_verified_logistics_20260305_211300_session/checkpoint_logistics.json` |

Do not cite this row as a final benchmark number. It is a checkpoint snapshot only.

## Provider Capability Notes

Local supplier observations from March 5:

- `/v1/models` exposed `gpt-5`, `gpt-5.1`, `gpt-5.1-codex`, `gpt-5.1-codex-mini`, `gpt-5.1-codex-max`, `gpt-5.2`, `gpt-5.2-codex`, `gpt-5-codex`, `gpt-5-codex-mini`, `gpt-5.3-codex`, `gpt-5.3-codex-spark`, and `gpt-5.4`
- `gpt-4o` was not available on this provider
- `gpt-5` accepted `reasoning_effort=low`
- `gpt-5` also worked with no `reasoning_effort`
- `gpt-5` rejected `reasoning_effort=xhigh` on this provider

These compatibility notes matter because they affect whether benchmark configurations are valid comparisons or just API errors.

## Historical Reference Runs

These are older reference numbers retained for context. They are not the newest March 5 artifacts.

### Gemini, Paper Canonical Numbers

| Date | Domain | Passed | Total | Accuracy | Artifact Note |
|------|--------|--------|-------|----------|---------------|
| 2026-02-13 | Blocksworld | ~200 | ~200 | ~99.8% | frozen paper artifact set |
| 2026-02-13 | Logistics | 568 | 570 | 99.6% | frozen paper artifact set |
| 2026-02-13 | Depots | 497 | 500 | 99.4% | frozen paper artifact set |

### GPT-5 via `infiniteai`, Earlier Full-Dataset Run

| Date | Domain | Success | Total | Accuracy | Note |
|------|--------|---------|-------|----------|------|
| 2026-02-23 | Blocksworld | 1103 | 1103 | 100.0% | historical run |
| 2026-02-23 | Logistics | 561 | 572 | 98.1% | historical run |
| 2026-02-23 | Depots | 493 | 501 | 98.4% | historical run |

## Current Interpretation

- On the static Logistics benchmark, the current completed supplier baseline is extremely strong: `gpt-5.3-codex` `BASELINE` reached 571/572.
- On the 5-instance generated slice, `gpt-5(low)` preserved 5/5 success while cutting average latency from 30.48s to 12.36s relative to `gpt-5` with no effort set.
- On the same 5-instance slice, `qwen3.5-plus` baseline is 2/5, but dynamic replanning reaches 5/5. For Qwen, repair is adding real value.
- The open research question is therefore not "can the strongest model plan at all?" but "when does the BDI plus verifier plus repair protocol outperform direct action-sequence generation enough to justify its overhead?"

## Reproduction Commands

Examples used for the runs above:

```bash
# Full Logistics baseline
python scripts/evaluation/run_planbench_full.py \
  --domain logistics \
  --execution_mode BASELINE \
  --parallel --workers 30

# Full Logistics BDI repair
python scripts/evaluation/run_planbench_full.py \
  --domain logistics \
  --execution_mode BDI_REPAIR \
  --parallel --workers 30

# 5-instance generated slice baseline
python scripts/evaluation/run_planbench_full.py \
  --domain logistics \
  --execution_mode BASELINE \
  --parallel --workers 5 \
  --instances /tmp/logistics_first5_generated.txt

# Dynamic replanning
python scripts/replanning/run_dynamic_replanning.py \
  --domain logistics \
  --parallel --workers 5
```
