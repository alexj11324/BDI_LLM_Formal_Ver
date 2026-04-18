#!/bin/bash
# submit_evals.sh — write ready_env + submit TP + PlanBench sbatch for Qwen3.6-35B-A3B.
#
# Usage:
#   bash scripts/psc_deploy/qwen36/submit_evals.sh <host> <port>
#
# Example:
#   bash scripts/psc_deploy/qwen36/submit_evals.sh w009 47260

set -euo pipefail

HOST="${1:?usage: submit_evals.sh <host> <port>}"
PORT="${2:?usage: submit_evals.sh <host> <port>}"

REPO=/ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver
STATUS=/ocean/projects/cis260113p/zjiang9/runs/status
MAN_DIR=/ocean/projects/cis260113p/zjiang9/runs/server_manifests
USER_SITE=/ocean/projects/cis260113p/zjiang9/python_user/lib/python3.12/site-packages

READY="$STATUS/qwen3.6-35b-a3b_ready_env.sh"
MANIFEST="$MAN_DIR/server_manifest_${HOST}_${PORT}.json"
TAG="${RUN_TAG:-qwen36_dual_$(date +%Y%m%d_%H%M)}"

mkdir -p "$STATUS" "$MAN_DIR"

cat > "$READY" <<EOF
export VLLM_HOST=$HOST
export VLLM_PORT=$PORT
export OPENAI_API_BASE=http://$HOST:$PORT/v1
export LLM_MODEL=openai/qwen3.6-35b-a3b
export MODEL_NAME=qwen3.6-35b-a3b
export MAX_MODEL_LEN_EFFECTIVE=32768
export SERVER_MANIFEST_PATH=$MANIFEST
EOF

cat > "$MANIFEST" <<EOF
{
  "source": "submit_evals.sh",
  "node": "$HOST",
  "port": $PORT,
  "openai_api_base": "http://$HOST:$PORT/v1",
  "served_model_name": "qwen3.6-35b-a3b",
  "model_repo": "Qwen/Qwen3.6-35B-A3B"
}
EOF

echo "[ready_env]  $READY"
echo "[manifest]   $MANIFEST"
echo "[run_tag]    $TAG"

if ! curl -fsS -m 5 "http://$HOST:$PORT/v1/models" > /dev/null; then
  echo "WARN: http://$HOST:$PORT/v1/models not responding — serve may still be loading." >&2
fi

cd "$REPO"
TP_JOB=$(sbatch --parsable --mem=15G \
  --export=ALL,RUN_TAG=$TAG,WORKERS=4,BDI_SERVICE_READY_ENV_FILE=$READY,LLM_MODEL=openai/qwen3.6-35b-a3b,PYTHONPATH=$USER_SITE \
  scripts/psc_deploy/qwen36/eval_travelplanner.sbatch)
echo "[submitted TP]        $TP_JOB  (RUN_TAG=$TAG)"

PB_JOB=$(sbatch --parsable \
  --export=ALL,RUN_TAG=$TAG,WORKERS=4,BDI_SERVICE_READY_ENV_FILE=$READY,LLM_MODEL=openai/qwen3.6-35b-a3b,PYTHONPATH=$USER_SITE \
  scripts/psc_deploy/qwen36/eval_planbench.sbatch)
echo "[submitted PlanBench] $PB_JOB  (RUN_TAG=$TAG)"

echo
squeue -u "$USER" -o "%.10i %.9P %.25j %.2t %.10M %R"
