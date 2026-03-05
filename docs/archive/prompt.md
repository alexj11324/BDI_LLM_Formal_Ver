# Verification-Only Evaluation Instructions

## Core Rules

1. **No Repair**: This is verification-only. Do NOT add repair/fix loops.
2. **Reuse Existing Code**: `scripts/run_verification_only.py` imports from `scripts/run_planbench_full.py`. Fix bugs in the verification script, not the full pipeline.
3. **NVIDIA NIM API**: Model is `openai/qwen/qwen2.5-7b-instruct` via `.env` config. Do NOT change `.env`.
4. **Checkpoint Support**: The verification script auto-checkpoints. If a task crashes, re-running resumes from checkpoint.
5. **Output**: Results go to `runs/verification_results/`. Each run produces a timestamped JSON.

## Workflow

- Complete exactly ONE task per iteration as defined in PRD.md.
- After completing a task, append progress to progress.txt.
- Follow the task numbering order (Task 1 → Task 2 → ... → Task 6).
- If a task involves running a long evaluation (Tasks 2-4), monitor progress and handle API errors gracefully.
- For Tasks 2-4: if the script crashes due to API timeout, simply re-run it — checkpoint auto-resume will skip completed instances.

## Verification

- After Task 1: verify the summary output makes sense (structural vs VAL agreement).
- After Tasks 2-4: verify result JSON exists and contains expected number of instances.
- After Task 5: run the analysis script and verify output tables are reasonable.
- After Task 6: verify `docs/experiment_results.md` exists with formatted tables.
