#!/bin/bash
#SBATCH -J glm47_serve
#SBATCH -A cis260113p
#SBATCH -p GPU-shared
#SBATCH --gres=gpu:h100-80:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH -t 04:00:00
#SBATCH -o /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/serve_%j.out
#SBATCH -e /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/serve_%j.err

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../bridges2_sbatch_under_review/psc_ocean_env.sh
source "${SCRIPT_DIR}/../bridges2_sbatch_under_review/psc_ocean_env.sh"

PROJECT="${BDI_PROJECT_ROOT}"
REPO_ROOT="${BDI_REPO_ROOT}"
SIF="${SIF:-${PROJECT}/apptainer/vllm_nightly.sif}"
HF_CACHE="${BDI_HF_HOME}"
CACHE_ROOT="${PROJECT}/vllm_runtime_cache"
RUN_ROOT="${BDI_RUN_ROOT}"
STATUS_ROOT="${BDI_STATUS_ROOT}"
MANIFEST_ROOT="${RUN_ROOT}/server_manifests"
LOG_DIR="${REPO_ROOT}/logs"
ACCESS_INFO=$LOG_DIR/serve_${SLURM_JOB_ID}_access.txt
READY_ENV=$STATUS_ROOT/glm47flash_service_ready_env.sh
SERVER_MANIFEST=$MANIFEST_ROOT/server_manifest_${SLURM_JOB_ID}.json

mkdir -p \
  "$LOG_DIR" \
  "$STATUS_ROOT" \
  "$MANIFEST_ROOT" \
  "$CACHE_ROOT"/{vllm,triton,xdg,xdg_config,torch_inductor,tmp}

NODE=$(hostname -s)
NODE_IP=$(hostname -I | awk '{print $1}')
MODEL_NAME=glm47flash
GPU_MEM_UTIL="${GPU_MEM_UTIL:-0.92}"
READINESS_TIMEOUT="${READINESS_TIMEOUT:-900}"
MAX_MODEL_LEN_CANDIDATES=(202752 131072 65536)
SERVER_PID=""
SELECTED_MAX_MODEL_LEN=""
FALLBACK_FROM=""
FALLBACK_REASON=""
ATTEMPT_LOGS=()

cleanup_server() {
  if [[ -n "${SERVER_PID:-}" ]] && kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    kill "${SERVER_PID}" >/dev/null 2>&1 || true
    wait "${SERVER_PID}" >/dev/null 2>&1 || true
  fi
}

trap cleanup_server EXIT

pick_free_port() {
  python - <<'PY'
import socket

with socket.socket() as sock:
    sock.bind(("", 0))
    print(sock.getsockname()[1])
PY
}

PORT="${PORT:-$(pick_free_port)}"

write_access_info() {
  cat > "$ACCESS_INFO" <<EOF
===== GLM-4.7-Flash vLLM Server (job $SLURM_JOB_ID) =====
Started: $(date)
Walltime: 4h (auto-terminate at end)
Node: $NODE ($NODE_IP)
Port: $PORT
Model: zai-org/GLM-4.7-Flash (served as "$MODEL_NAME")
Effective max-model-len: ${SELECTED_MAX_MODEL_LEN}
Server manifest: $SERVER_MANIFEST
Ready env: $READY_ENV

--- Access Method 1: from another Bridges2 login/compute node ---
curl http://$NODE:$PORT/v1/models
curl -X POST http://$NODE:$PORT/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{"model":"$MODEL_NAME","messages":[{"role":"user","content":"hello"}]}'

--- Access Method 2: SSH tunnel from your laptop ---
ssh -L $PORT:$NODE:$PORT bridges2
# then on laptop: curl http://localhost:$PORT/v1/models

--- How to stop ---
scancel $SLURM_JOB_ID
EOF
}

write_ready_env() {
  cat > "$READY_ENV" <<EOF
export VLLM_HOST=$NODE
export VLLM_PORT=$PORT
export OPENAI_API_BASE=http://$NODE:$PORT/v1
export LLM_MODEL=openai/$MODEL_NAME
export MODEL_NAME=$MODEL_NAME
export MAX_MODEL_LEN_EFFECTIVE=$SELECTED_MAX_MODEL_LEN
export SERVER_MANIFEST_PATH=$SERVER_MANIFEST
EOF
}

write_server_manifest() {
  local active_log="$1"
  local attempt_logs_json
  attempt_logs_json="$(printf '%s\n' "${ATTEMPT_LOGS[@]}" | python -c 'import json,sys; print(json.dumps([line.strip() for line in sys.stdin if line.strip()]))')"
  python - <<PY
import json
from pathlib import Path

payload = {
    "job_id": "${SLURM_JOB_ID}",
    "node": "${NODE}",
    "node_ip": "${NODE_IP}",
    "port": ${PORT},
    "openai_api_base": "http://${NODE}:${PORT}/v1",
    "model_repo": "zai-org/GLM-4.7-Flash",
    "served_model_name": "${MODEL_NAME}",
    "seed": 42,
    "dtype": "bfloat16",
    "gpu_memory_utilization": float("${GPU_MEM_UTIL}"),
    "max_model_len_effective": int("${SELECTED_MAX_MODEL_LEN}"),
    "fallback_from": "${FALLBACK_FROM}",
    "fallback_reason": "${FALLBACK_REASON}",
    "server_log": "${active_log}",
    "access_info": "${ACCESS_INFO}",
    "ready_env": "${READY_ENV}",
    "attempt_logs": ${attempt_logs_json},
}
Path("${SERVER_MANIFEST}").write_text(json.dumps(payload, indent=2) + "\\n")
PY
}

wait_for_server_ready() {
  local active_log="$1"
  local waited=0
  while ! curl -fsS "http://127.0.0.1:${PORT}/v1/models" >/dev/null 2>&1; do
    if [[ -n "${SERVER_PID:-}" ]] && ! kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
      echo "vLLM process exited before becoming ready" >&2
      tail -n 120 "${active_log}" >&2 || true
      return 1
    fi
    sleep 5
    waited=$((waited + 5))
    if (( waited >= READINESS_TIMEOUT )); then
      echo "Timed out waiting for server readiness after ${READINESS_TIMEOUT}s" >&2
      tail -n 120 "${active_log}" >&2 || true
      return 1
    fi
  done
  return 0
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
      echo '>>> starting persistent vllm serve on port $PORT'
      exec vllm serve zai-org/GLM-4.7-Flash \
        --tensor-parallel-size 1 \
        --seed 42 \
        --dtype bfloat16 \
        --disable-log-requests \
        --max-model-len ${candidate} \
        --gpu-memory-utilization ${GPU_MEM_UTIL} \
        --port $PORT \
        --host 0.0.0.0 \
        --reasoning-parser glm45 \
        --tool-call-parser glm47 \
        --enable-auto-tool-choice \
        --served-model-name ${MODEL_NAME}
    " > "${active_log}" 2>&1 &
  SERVER_PID=$!
}

echo "===== $NODE | JOB $SLURM_JOB_ID | $(date) ====="
echo "Repository root: $REPO_ROOT"
echo "Manifest path: $SERVER_MANIFEST"

for candidate in "${MAX_MODEL_LEN_CANDIDATES[@]}"; do
  ACTIVE_LOG="$LOG_DIR/vllm_server_${SLURM_JOB_ID}_max${candidate}.log"
  ATTEMPT_LOGS+=("$ACTIVE_LOG")
  echo ">>> trying max-model-len=${candidate}"
  start_server_attempt "$candidate" "$ACTIVE_LOG"

  if wait_for_server_ready "$ACTIVE_LOG"; then
    SELECTED_MAX_MODEL_LEN="$candidate"
    if [[ "$candidate" != "${MAX_MODEL_LEN_CANDIDATES[0]}" ]]; then
      FALLBACK_FROM="${MAX_MODEL_LEN_CANDIDATES[0]}"
      FALLBACK_REASON="fallback_after_startup_failure_on_${MAX_MODEL_LEN_CANDIDATES[0]}"
    fi
    write_access_info
    write_ready_env
    write_server_manifest "$ACTIVE_LOG"

    echo "===== READY | job $SLURM_JOB_ID | max-model-len=${SELECTED_MAX_MODEL_LEN} ====="
    cat "$ACCESS_INFO"
    wait "$SERVER_PID"
    exit $?
  fi

  cleanup_server
done

echo "All max-model-len candidates failed: ${MAX_MODEL_LEN_CANDIDATES[*]}" >&2
exit 1
