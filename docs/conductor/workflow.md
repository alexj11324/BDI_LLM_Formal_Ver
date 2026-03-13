# Workflow

## TDD Policy
**Moderate**: Tests encouraged for core pipeline logic (verifier, repair engine, domain specs). Not required for evaluation scripts and paper generation utilities.

## Commit Strategy
**Conventional Commits**: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:` prefixes required.

## Code Review
**Required for non-trivial changes**: All changes to `src/bdi_llm/planner/`, `src/bdi_llm/symbolic_verifier.py`, and `src/bdi_llm/plan_repair.py` require review. Evaluation scripts and documentation changes are self-review OK.

## Verification Checkpoints
- After each benchmark evaluation run: verify results against `RESULTS_PROVENANCE.md`
- Before merging: run `pytest tests/` (unit + smoke)
- Before paper submission: full PlanBench + TravelPlanner evaluation
