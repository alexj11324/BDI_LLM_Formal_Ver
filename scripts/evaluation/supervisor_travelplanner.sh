#!/bin/bash
# Supervisor: keeps 2 sessions running at a time, auto-queues next when one finishes.
# Usage: nohup bash supervisor_travelplanner.sh &

set -euo pipefail
cd ~/BDI_LLM_Formal_Ver
OUT=runs/tp_full
mkdir -p "$OUT"

# Job queue: "name split script"
JOBS=(
  "val_baseline  validation scripts/evaluation/run_travelplanner_baseline.py"
  "val_bdi       validation scripts/evaluation/run_travelplanner_bdi.py"
  "test_repair   test       scripts/evaluation/run_travelplanner_repair.py"
  "val_repair    validation scripts/evaluation/run_travelplanner_repair.py"
)

MAX_CONCURRENT=2
WORKERS=200
declare -A PIDS  # name -> pid

log() { echo "[$(date '+%H:%M:%S')] $*"; }

start_job() {
  local name split script
  read -r name split script <<< "$1"
  log "STARTING $name (split=$split)"
  python3 "$script" --split "$split" --output_dir "$OUT" --workers "$WORKERS" \
    > "$OUT/${name}.log" 2>&1 &
  PIDS["$name"]=$!
  log "  PID=${PIDS[$name]}"
}

job_idx=0
running=0

# Wait for existing test/baseline and test/bdi to finish first
log "Supervisor started. Waiting for existing tp_baseline & tp_bdi tmux sessions..."
while true; do
  # Check if tmux sessions still exist
  bl_alive=$(tmux has-session -t tp_baseline 2>/dev/null && echo 1 || echo 0)
  bdi_alive=$(tmux has-session -t tp_bdi 2>/dev/null && echo 1 || echo 0)
  total_alive=$((bl_alive + bdi_alive))

  slots=$((MAX_CONCURRENT - total_alive - running))

  while [ "$slots" -gt 0 ] && [ "$job_idx" -lt "${#JOBS[@]}" ]; do
    start_job "${JOBS[$job_idx]}"
    job_idx=$((job_idx + 1))
    running=$((running + 1))
    slots=$((slots - 1))
  done

  # Check if our managed jobs finished
  for name in "${!PIDS[@]}"; do
    pid=${PIDS[$name]}
    if ! kill -0 "$pid" 2>/dev/null; then
      wait "$pid" 2>/dev/null
      ec=$?
      log "FINISHED $name (exit=$ec)"
      unset PIDS["$name"]
      running=$((running - 1))
    fi
  done

  # All done?
  if [ "$total_alive" -eq 0 ] && [ "$running" -eq 0 ] && [ "$job_idx" -ge "${#JOBS[@]}" ]; then
    log "ALL 6 SESSIONS COMPLETE"
    break
  fi

  sleep 15
done
