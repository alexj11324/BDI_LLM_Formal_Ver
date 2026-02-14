# Repo Organization

This document defines the storage and maintenance boundaries for this repository.

## Directory Responsibilities

- `src/bdi_llm/`: core framework code (planner, verifiers, repair logic, schemas).
- `scripts/`: runnable utilities and benchmark entrypoints.
- `tests/`: unit/integration tests.
- `planbench_data/`: benchmark inputs and validator tooling.
- `runs/`: mutable run outputs and ad-hoc experiment products.
  - `runs/planbench_results/`: default output dir for `scripts/run_planbench_full.py`.
  - `runs/legacy/planbench_results_20260211/`: historical pre-freeze run outputs kept for debugging.
- `planbench_results/` (repo root): legacy output location from older scripts (ignored by git if present).
- `artifacts/paper_eval_20260213/`: immutable paper evidence snapshot.
- `docs/`: user docs, architecture notes, and provenance.
- `BDI_Paper/`: paper source content.

## Mutability Policy

- Treat `runs/` as non-canonical and overwriteable.
- Treat root-level `planbench_results/` as legacy non-canonical output if it exists locally.
- Treat `artifacts/paper_eval_20260213/` as canonical for paper numbers.
- Do not derive paper tables directly from `runs/`.
- Keep raw source archive `planbench_results_archive.tar.gz` for back-tracing.

## Paper Result Workflow

1. Extract frozen evidence files into `artifacts/paper_eval_20260213/`.
2. Verify integrity and counts with:

```bash
python scripts/verify_paper_eval_snapshot.py
```

3. Use only checkpoint files in the frozen artifact directory for paper metrics.

## Housekeeping

Safe local cleanup for temporary/cache files:

```bash
rm -rf .pytest_cache scripts/__pycache__ src/bdi_llm/__pycache__ tests/__pycache__ .DS_Store docs/.DS_Store
```

Keep cleanup limited to caches and generated files unless explicitly requested otherwise.
