---
name: verify-fast
description: Run offline unit tests + ruff lint to quickly verify code changes before commit. Skips integration tests that need API keys or VAL binary. Use when user says "verify", "check before commit", or after non-trivial code edits.
---

Quick verification gate for the BDI-LLM repo. Run BEFORE marking a task done or proposing a commit.

## Steps

1. Offline unit tests:
   ```bash
   pytest tests/unit -q
   ```
   These are fast (<60s typical).

2. Ruff lint:
   ```bash
   ruff check .
   ```

3. Ruff format check (no auto-rewrite):
   ```bash
   ruff format --check .
   ```

## Pass criteria
- pytest exits 0, no failures
- ruff check exits 0 (or only acceptable warnings — never silently bypass)
- ruff format --check exits 0 (else ask the user before reformatting)

## Out of scope
- `tests/integration/` — needs API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.) or a working VAL binary at `workspaces/planbench_data/planner_tools/VAL/validate`. Run separately when credentials are present.
- TravelPlanner runners — need `TRAVELPLANNER_HOME` and the external dataset.
- PSC eval jobs — those run on Bridges2 via SLURM, not part of local verify.

## On failure
- Investigate root cause; do not mass-rewrite tests.
- Ruff lint failures: prefer `ruff check --fix` for safe fixes; manual edit for E/W/F that --fix can't resolve.
- Do NOT run the full `pytest` (no path filter) instead of `pytest tests/unit` — the full suite includes integration tests that fail without credentials and pollute signal.
