# Paper Result Provenance (Gemini 3 Flash)

This document freezes the evidence chain for paper-reported PlanBench metrics.

## Snapshot Location

- Frozen snapshot directory:
  - `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/artifacts/paper_eval_20260213/`
- Source archive:
  - `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/planbench_results_archive.tar.gz`
- Integrity manifest:
  - `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/artifacts/paper_eval_20260213/MANIFEST.json`

## Model Configuration Source

- Config file:
  - `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/.env`
- Model used for this snapshot:
  - `LLM_MODEL=vertex_ai/gemini-3-flash-preview`

## Primary Paper Data Source

Use checkpoint files as the canonical source for paper tables:

- `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/artifacts/paper_eval_20260213/checkpoint_blocksworld.json`
- `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/artifacts/paper_eval_20260213/checkpoint_logistics.json`
- `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/artifacts/paper_eval_20260213/checkpoint_depots.json`

Recomputed from per-instance `success` values:

- Blocksworld: `200/200` (100.0%)
- Logistics: `568/570` (99.6%)
  - Failed instances: `instance-166.pddl`, `instance-228.pddl`
- Depots: `497/500` (99.4%)
  - Failed instances: `instance-173.pddl`, `instance-179.pddl`, `instance-187.pddl`
- Overall: `1265/1270 = 99.6%`

## Upstream Results (Non-Canonical for Paper Tables)

The following are retained as upstream run records only:

- `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/artifacts/paper_eval_20260213/results_blocksworld_20260212_214230.json`
- `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/artifacts/paper_eval_20260213/results_logistics_20260213_025757.json`
- `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/artifacts/paper_eval_20260213/results_depots_20260213_014014.json`

Relationship to checkpoint files:

- Logistics: relative to `checkpoint_logistics.json`, `results_logistics_20260213_025757.json` has one extra row each for:
  - `instance-259.pddl`
  - `instance-264.pddl`
- Depots: `results_depots_20260213_014014.json` contains one extra successful instance not included in checkpoint:
  - `instance-183.pddl`

## Verification

Run:

```bash
python /Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/scripts/verify_paper_eval_snapshot.py
```

Validation includes:

- required files exist
- `sha256` matches `MANIFEST.json`
- recomputed counts match checkpoint paper numbers
- failed-instance IDs match paper claims
- upstream-vs-checkpoint relationship checks (logistics duplicate rows, depots extra row)

## Why This Prevents Future Drift

`/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/results/planbench_results/` can be overwritten by later experiments. The frozen snapshot in `/Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/artifacts/paper_eval_20260213/` is the immutable evidence package for publication.
