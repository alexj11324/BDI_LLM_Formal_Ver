---
name: psc-eval-status
description: Snapshot current Bridges2 PSC SLURM jobs and the most recent TravelPlanner / PlanBench eval checkpoint. Use when user asks "what's the eval status", "how is the run going", or before submitting new jobs.
---

Read-only status snapshot for ongoing PSC evals. Never submits, never kills.

## Steps

1. SLURM queue (use scontrol — squeue cache lags across login nodes):
   ```bash
   ssh bridges2 "scontrol show job -d \$(squeue -u \$USER -h -o %i | tr '\\n' ',') 2>/dev/null | head -200"
   ```

2. Latest TravelPlanner eval checkpoints:
   ```bash
   ssh bridges2 "ls -lt /ocean/projects/cis260113p/zjiang9/runs/tp_*/checkpoint*.json 2>/dev/null | head -5"
   ```
   Cat the newest one, report `progress`, `n_done`, `n_total`, `silent_failure_rate` if present.

3. Latest PlanBench eval results:
   ```bash
   ssh bridges2 "ls -lt /ocean/projects/cis260113p/zjiang9/runs/pb_*/results.json 2>/dev/null | head -5"
   ```

4. Cross-reference each eval to its served model: read `BDI_SERVICE_READY_ENV_FILE` inside each run dir to confirm the endpoint.

## Output format

- Active jobs: `jobid · partition · state · time_used / requested · job_name`
- TP eval: `<run_tag> · <progress>% · silent_failure_rate=<x>% · model=<host:port>`
- PB eval: `<run_tag> · per-mode VAL pass rate (bdi-only / bdi-repair / oracle / vanilla) · model=<host:port>`
- Stop monitors when jobs reach a terminal state (per auto-memory `feedback_monitor_lifecycle`).

## Don't
- Submit new sbatch jobs from this skill — needs explicit user approval.
- `scancel` running jobs.
- Modify any ready_env file.
- Reach for `squeue` alone for decisions — its multi-login-node cache lags. Always anchor to `scontrol show job`.
