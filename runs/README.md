# Runs Directory Guide

This folder contains non-canonical experiment outputs and summaries.

## Canonical vs Non-Canonical

- Canonical paper evidence (use for paper tables):
  - `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/artifacts/paper_eval_20260213/`
- Non-canonical run outputs (can be overwritten by new runs):
  - `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/runs/`
  - Legacy root-level `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/planbench_results/` may still exist from older scripts.

## Legacy Snapshot (Pre-Freeze)

- Historical 2026-02-11 run outputs are preserved at:
  - `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/runs/legacy/planbench_results_20260211/`

These files are kept for debugging and regression comparison only.
Do not use them as the primary source for paper numbers.

## Quick Rule

If you need publication numbers, always start from:

- `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/artifacts/paper_eval_20260213/checkpoint_blocksworld.json`
- `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/artifacts/paper_eval_20260213/checkpoint_logistics.json`
- `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/artifacts/paper_eval_20260213/checkpoint_depots.json`
