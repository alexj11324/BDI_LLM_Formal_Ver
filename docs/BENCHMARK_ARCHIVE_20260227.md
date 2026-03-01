# Benchmark Archive (2026-02-27)

This archive marks benchmark parts that have already been executed and should be skipped by default in future runs.

## Lock File

- Machine-readable lock: `runs/completed_benchmarks.lock.json`
- Policy: skip all listed groups by default; rerun only with explicit user instruction.

## Archived Completed Groups

1. PlanBench baseline (`scientist_team`)
   - `blocksworld`: 1103 evaluated, 1103 success
   - `logistics`: 572 evaluated, 561 success
   - `depots`: 501 evaluated, 493 success

2. Ablation benchmark
   - `NAIVE`: 4/4
   - `BDI_ONLY`: 4/4
   - `FULL_VERIFIED`: 0/4

3. Regression gate
   - `logistics`: 11 evaluated, 0 resolved
   - `depots`: 8 evaluated, 0 resolved

4. SWE-bench benchmark
   - `limit=1`: 1 evaluated, 0 passed

## Domain-Level Do-Not-Run Rules

- Obfuscated domains are disabled and should not be run:
  - `obfuscated_*`
  - `runs/disabled_obfuscated/`

## Reference Report

- Canonical report: `runs/scientist_team/reports/final_report.json`
