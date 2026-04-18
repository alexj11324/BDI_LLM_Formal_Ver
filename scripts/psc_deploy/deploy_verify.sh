#!/bin/bash
#SBATCH -J glm47_deploy_verify
#SBATCH -A cis260113p
#SBATCH -p GPU-shared
#SBATCH --gres=gpu:h100-80:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH -t 01:00:00
#SBATCH -o /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/glm47_verify_%j.out
#SBATCH -e /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/glm47_verify_%j.err

set -euo pipefail

PROJECT=/ocean/projects/cis260113p/zjiang9
REPO_ROOT=$PROJECT/repo/BDI_LLM_Formal_Ver
SIF=$PROJECT/apptainer/vllm_nightly.sif
HF_CACHE=$PROJECT/hf_cache
CACHE_ROOT=$PROJECT/vllm_runtime_cache
RUN_ROOT=$REPO_ROOT/runs
MANIFEST_ROOT=$RUN_ROOT/server_manifests
LOG_DIR=$REPO_ROOT/logs
SERVER_MANIFEST=$MANIFEST_ROOT/server_manifest_verify_${SLURM_JOB_ID}.json

mkdir -p \
  "$LOG_DIR" \
  "$MANIFEST_ROOT" \
  "$CACHE_ROOT"/{vllm,triton,xdg,xdg_config,torch_inductor,tmp}

PORT=$((8000 + SLURM_JOB_ID % 1000))
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.92}"
READINESS_TIMEOUT="${READINESS_TIMEOUT:-900}"
MAX_MODEL_LEN_CANDIDATES=(202752 131072 65536)
SERVER_PID=""
SELECTED_MAX_MODEL_LEN=""
FALLBACK_FROM=""
FALLBACK_REASON=""

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

write_server_manifest() {
  local active_log="$1"
  python - <<PY
import json
from pathlib import Path

payload = {
    "job_id": "${SLURM_JOB_ID}",
    "node": "$(hostname -s)",
    "port": ${PORT},
    "openai_api_base": "http://127.0.0.1:${PORT}/v1",
    "model_repo": "zai-org/GLM-4.7-Flash",
    "served_model_name": "glm47flash",
    "seed": 42,
    "dtype": "bfloat16",
    "gpu_memory_utilization": float("${GPU_MEM_UTIL}"),
    "max_model_len_effective": int("${SELECTED_MAX_MODEL_LEN}"),
    "fallback_from": "${FALLBACK_FROM}",
    "fallback_reason": "${FALLBACK_REASON}",
    "server_log": "${active_log}",
}
Path("${SERVER_MANIFEST}").write_text(json.dumps(payload, indent=2) + "\\n")
PY
}

wait_for_server_ready() {
  local active_log="$1"
  local waited=0
  until curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; do
    if [[ -n "${SERVER_PID:-}" ]] && ! kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
      tail -n 120 "${active_log}" >&2 || true
      return 1
    fi
    sleep 5
    waited=$((waited + 5))
    if (( waited >= READINESS_TIMEOUT )); then
      tail -n 120 "${active_log}" >&2 || true
      return 1
    fi
  done
}

start_server_attempt() {
  local candidate="$1"
  local active_log="$2"
  apptainer exec --nv --writable-tmpfs \
    --env HF_HOME=/hf_cache \
    --env HF_HUB_CACHE=/hf_cache/hub \
    --env HUGGINGFACE_HUB_CACHE=/hf_cache/hub \
    --env HF_HUB_OFFLINE=1 \
    --env VLLM_WORKER_MULTIPROC_METHOD=spawn \
    --env VLLM_CACHE_ROOT=/cache/vllm \
    --env VLLM_NO_USAGE_STATS=1 \
    --env VLLM_DO_NOT_TRACK=1 \
    --env TRITON_CACHE_DIR=/cache/triton \
    --env XDG_CACHE_HOME=/cache/xdg \
    --env XDG_CONFIG_HOME=/cache/xdg_config \
    --env TORCHINDUCTOR_CACHE_DIR=/cache/torch_inductor \
    --env TMPDIR=/cache/tmp \
    --env PIP_NO_CACHE_DIR=1 \
    --env PIP_DISABLE_PIP_VERSION_CHECK=1 \
    -B "$HF_CACHE":/hf_cache \
    -B "$CACHE_ROOT":/cache \
    "$SIF" \
    bash -c "
      pip install --quiet 'pandas==2.2.3' 'pyarrow==17.0.0' 2>&1 | tail -3
      exec vllm serve zai-org/GLM-4.7-Flash \
        --tensor-parallel-size 1 \
        --seed 42 \
        --dtype bfloat16 \
        --disable-log-requests \
        --max-model-len ${candidate} \
        --gpu-memory-utilization ${GPU_MEM_UTIL} \
        --port ${PORT} \
        --host 0.0.0.0 \
        --served-model-name glm47flash
    " > "${active_log}" 2>&1 &
  SERVER_PID=$!
}

echo "===== NODE $(hostname) | JOB $SLURM_JOB_ID | $(date) ====="
nvidia-smi -L
ls -lh "$SIF"

for candidate in "${MAX_MODEL_LEN_CANDIDATES[@]}"; do
  ACTIVE_LOG="$LOG_DIR/vllm_verify_${SLURM_JOB_ID}_max${candidate}.log"
  echo ">>> trying max-model-len=${candidate}"
  start_server_attempt "$candidate" "$ACTIVE_LOG"
  if wait_for_server_ready "$ACTIVE_LOG"; then
    SELECTED_MAX_MODEL_LEN="$candidate"
    if [[ "$candidate" != "${MAX_MODEL_LEN_CANDIDATES[0]}" ]]; then
      FALLBACK_FROM="${MAX_MODEL_LEN_CANDIDATES[0]}"
      FALLBACK_REASON="fallback_after_startup_failure_on_${MAX_MODEL_LEN_CANDIDATES[0]}"
    fi
    write_server_manifest "$ACTIVE_LOG"
    break
  fi
  cleanup
done

if [[ -z "${SELECTED_MAX_MODEL_LEN}" ]]; then
  echo "Failed to start server with any max-model-len candidate" >&2
  exit 1
fi

curl -fsS "http://127.0.0.1:${PORT}/v1/models"

for idx in 1 2 3; do
  curl -fsS -X POST "http://127.0.0.1:${PORT}/v1/chat/completions" \
    -H "Content-Type: application/json" \
    -d '{
      "model": "glm47flash",
      "messages": [{"role":"user","content":"Introduce yourself in one English sentence."}],
      "max_tokens": 80,
      "temperature": 0.0,
      "seed": 42
    }' > "${LOG_DIR}/glm47_verify_${SLURM_JOB_ID}_resp_${idx}.json"
done

cmp -s \
  "${LOG_DIR}/glm47_verify_${SLURM_JOB_ID}_resp_1.json" \
  "${LOG_DIR}/glm47_verify_${SLURM_JOB_ID}_resp_2.json"
cmp -s \
  "${LOG_DIR}/glm47_verify_${SLURM_JOB_ID}_resp_2.json" \
  "${LOG_DIR}/glm47_verify_${SLURM_JOB_ID}_resp_3.json"

echo "[$(date)] [DONE] Deployment verification OK"
echo "Server manifest: ${SERVER_MANIFEST}"
