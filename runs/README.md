# Runs Directory Guide

This folder contains non-canonical experiment outputs and summaries.

## Rerun Policy (Important)

- Completed benchmark groups are tracked in:
  - `./runs/completed_benchmarks.lock.json`
- Default behavior:
  - Skip rerunning anything listed in that lock file.
- Rerun exception:
  - Only rerun when the user explicitly asks in the current task.
- Disabled domains:
  - `obfuscated_*` (including `./runs/disabled_obfuscated/`) are disabled by default and should not be run.

## Canonical vs Non-Canonical

- Canonical paper evidence (use for paper tables):
  - `./artifacts/paper_eval_20260213/`
- Non-canonical run outputs (can be overwritten by new runs):
  - `./runs/`
  - Legacy root-level `./planbench_results/` may still exist from older scripts.

## Legacy Snapshot (Pre-Freeze)

- Historical 2026-02-11 run outputs are preserved at:
  - `./runs/legacy/planbench_results_20260211/`

These files are kept for debugging and regression comparison only.
Do not use them as the primary source for paper numbers.

## Quick Rule

If you need publication numbers, always start from:

- `./artifacts/paper_eval_20260213/checkpoint_blocksworld.json`
- `./artifacts/paper_eval_20260213/checkpoint_logistics.json`
- `./artifacts/paper_eval_20260213/checkpoint_depots.json`
