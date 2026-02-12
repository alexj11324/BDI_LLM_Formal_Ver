# Repository Reorganization Walkthrough

I have reorganized the repository structure to be cleaner and more maintainable.

## Changes Made

### 1. Documentation & Reports
Moved all top-level report and markdown files to `docs/reports/`.
- `ADD_Sym.md`, `LLM_DEMO_RESULTS.md`, etc. within `docs/reports/`.

### 2. Scripts
Moved top-level Python and Shell scripts to `scripts/`.
- `run_evaluation.py`, `run_planbench_full.py`, etc.
- **Fixed Imports**: Updated `sys.path` in these scripts to correctly locate the `src` package from the new location.

### 3. Tests
Moved integration tests from root to `tests/`.
- `test_symbolic_verifier.py` (root) -> `tests/test_symbolic_verifier_integration.py`
- `test_integrated_verification.py` -> `tests/test_integrated_verification.py`
- `test_integration_phase2.py` -> `tests/test_integration_phase2.py`
- **Fixed Imports**: Updated `sys.path` in these tests.

### 4. Results
Moved output files to `results/`.
- `benchmark_results.json`, plots, and `planbench_results/` directory.

### 5. Cleanup
- Moved `firebase-debug.log` and temporary PDDL files to `tmp/`.

## Verification
I verified that the scripts can correctly import the project modules from their new locations.
For example, running `python3 scripts/run_evaluation.py --help` now correctly resolves `from bdi_llm...` imports (although it may require `pydantic` installed to run fully).

## New Structure
```
.
├── docs
│   └── reports
├── scripts
│   ├── run_evaluation.py
│   └── ...
├── src
│   └── bdi_llm
├── tests
│   ├── test_symbolic_verifier_integration.py
│   └── ...
├── results
├── tmp
└── ...
```
