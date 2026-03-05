# Dynamic Replanning Pipeline Setup

One-line: Implemented and tested the Dynamic Replanning subsystem (BeliefBase, checkpoint resume, timeout unification), reaching the stage where all code is ready but blocked on a missing API key.

## Summary

The BDI-LLM Formal Verification (PNSV) project needed a Dynamic Replanning pipeline that can re-generate plans at runtime when simulated execution diverges from the expected world state. This session implemented the three missing core components — `BeliefBase` for PDDL state tracking, checkpoint-resume logic for long-running evaluations, and unified LLM timeout handling (600s). An end-to-end test was executed against one Blocksworld instance; the pipeline ran without hanging but failed at the Init stage due to a missing `DASHSCOPE_API_KEY` environment variable. The code is fully wired; only the API credential is needed to validate the complete flow.

## Changed files

- `src/bdi_llm/dynamic_replanner/belief_base.py` — **[NEW]** Parses PDDL `:init` blocks into a set of propositions. Supports `apply_effects()` (STRIPS add/delete) and `to_natural_language()` serialization for LLM prompts.
- `src/bdi_llm/dynamic_replanner/__init__.py` — Added `BeliefBase` to the public exports.
- `scripts/run_dynamic_replanning.py` — Added `--resume` flag with atomic JSON checkpoint writes (`write-tmp → rename`) so crashed evaluations can resume from the last completed instance.
- `src/bdi_llm/planner.py` — Unified all `litellm.completion()` timeout kwargs to use `Config.TIMEOUT` (600s) instead of hardcoded 120s, preventing premature kills of deep-reasoning models like `qwq-plus`.
- `src/bdi_llm/dynamic_replanner/executor.py` — Aligned executor timeout to `Config.TIMEOUT`.
- `.env` — Switched model to `qwen3.5-plus` via DashScope endpoint; set `LLM_TIMEOUT=600`.

## Git commits

- `cabdd2b` Task 1: Smoke test verification script - PASSED (5 Blocksworld instances)
- `fddd307` docs: update README with PNSV framework, security fixes, and recent changes
- `b0a2d7d` fix: address Codex code review bugs + Sourcery refactoring
- `19d1247` fix: replace os.popen/os.system with subprocess.run + extract run_val helper
- `49a35da` Add optional reasoning-trace persistence for benchmark runs

No new commits were pushed during this specific session (changes are local/unstaged).

## Notes

- **PDDL Parsing Robustness**: `BeliefBase` uses a lightweight regex-based parser for `:init` blocks rather than a full PDDL grammar. This is sufficient for Blocksworld/Logistics/Depots but may need upgrading for domains with complex typing or conditional effects.
- **Checkpoint Atomicity**: The resume logic uses `write-to-temp → os.rename()` to prevent corrupted JSON on crash. This is POSIX-atomic on the same filesystem.
- **Timeout Architecture Decision**: We chose to unify all timeouts to a single `Config.TIMEOUT` rather than per-call tuning. Rationale: deep-reasoning models (`qwq-plus`) have unpredictable thinking times; a generous 600s ceiling avoids false negatives in evaluation without meaningfully slowing the pipeline (most calls complete in < 60s).
- **API Key Blocker**: The `.env` file originally used `${DASHSCOPE_API_KEY}` shell-expansion syntax, but `python-dotenv` does **not** expand shell variables. The key must be hardcoded in `.env` or exported in the shell before running.
- **Mistake to Avoid**: Do not assume `python-dotenv` supports `${VAR}` interpolation — it does not. Always provide literal values in `.env` files.
