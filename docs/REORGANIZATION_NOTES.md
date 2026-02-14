# Reorganization Notes

This note captures repository-level cleanup decisions to keep structure and ownership consistent.

## What was standardized

1. **Testing style**
   - `tests/test_plan_repair.py` is now pure pytest style.
   - Removed script-like `run_all_tests()` and inline `print` side effects.
   - Added a public-behavior regression test for virtual node deduplication through `PlanRepairer.repair()`.

2. **Project map alignment**
   - `PROJECT_OVERVIEW.md` now matches actual repository directories (`runs/`, `artifacts/`, `docs/`, etc.) and current mutability model.

## Follow-up suggestions

- Introduce a small `Makefile` with `test`, `lint`, and `verify-snapshot` targets.
- Add a dedicated `tests/unit/` and `tests/integration/` split as test count grows.
- Consider moving historical/one-off scripts under `scripts/legacy/` and keeping `scripts/` for actively supported entrypoints only.
