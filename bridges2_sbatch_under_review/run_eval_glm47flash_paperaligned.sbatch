#!/bin/bash
#SBATCH --job-name=glm47_pb_eval
#SBATCH --account=cis260113p
#SBATCH --partition=RM-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=06:00:00
#SBATCH --output=/ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/glm47_pb_eval_%j.out
#SBATCH --error=/ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/glm47_pb_eval_%j.err

set -euo pipefail

module purge
module load anaconda3/2024.10-1
source /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/bridges2_sbatch_under_review/psc_ocean_env.sh

set -a
source "${BDI_REPO_ROOT}/bridges2_sbatch_under_review/bdi_env.env"
set +a

if [[ ! -f "${BDI_SERVICE_READY_ENV_FILE}" ]]; then
  echo "Missing GPU service ready env: ${BDI_SERVICE_READY_ENV_FILE}" >&2
  echo "Start scripts/psc_deploy/serve_persistent.sh first." >&2
  exit 1
fi

set -a
source "${BDI_SERVICE_READY_ENV_FILE}"
set +a

: "${VLLM_HOST:?VLLM_HOST missing from service ready env}"
: "${VLLM_PORT:?VLLM_PORT missing from service ready env}"
: "${OPENAI_API_BASE:?OPENAI_API_BASE missing from service ready env}"
: "${SERVER_MANIFEST_PATH:?SERVER_MANIFEST_PATH missing from service ready env}"

DOMAIN="${DOMAIN:-blocksworld}"
RUN_TAG="${RUN_TAG:-glm47flash_eval_$(date +%Y%m%d)}"
OUT_ROOT="${BDI_RUN_ROOT}/${RUN_TAG}/${DOMAIN}"
MANIFEST_OUT="${OUT_ROOT}/run_manifest_${DOMAIN}.json"
OPENAI_MODELS_URL="${OPENAI_API_BASE}/models"

mkdir -p "${OUT_ROOT}"

export OPENAI_API_KEY="${OPENAI_API_KEY:-EMPTY}"
export LLM_MODEL="${LLM_MODEL:-openai/glm47flash}"
export SAVE_REASONING_TRACE="${SAVE_REASONING_TRACE:-1}"
export REASONING_TRACE_MAX_CHARS="${REASONING_TRACE_MAX_CHARS:-20000}"
export PYTHONPATH="${BDI_REPO_ROOT}:${PYTHONPATH:-}"

echo "=== RM PlanBench evaluation ==="
echo "Node: $(hostname)"
echo "Domain: ${DOMAIN}"
echo "Run tag: ${RUN_TAG}"
echo "Output root: ${OUT_ROOT}"
echo "Service env: ${BDI_SERVICE_READY_ENV_FILE}"
echo "Service manifest: ${SERVER_MANIFEST_PATH}"
echo "OPENAI_API_BASE=${OPENAI_API_BASE}"
date
print_storage_snapshot "before RM eval"

wait_for_openai_compat "${OPENAI_MODELS_URL}" 120
curl -fsS "${OPENAI_MODELS_URL}"

cd "${BDI_REPO_ROOT}"

CMD=(
  python scripts/evaluation/_legacy/run_planbench_full.py
  --domain "${DOMAIN}"
  --output_dir "${OUT_ROOT}"
  --execution_mode bdi-repair
  --deterministic
  --disable_repair_cache
  --disable_early_exit
  --manifest_out "${MANIFEST_OUT}"
)

if [[ -n "${MAX_INSTANCES:-}" ]]; then
  CMD+=(--max_instances "${MAX_INSTANCES}")
fi

if [[ -n "${INSTANCES_FILE:-}" ]]; then
  CMD+=(--instances "${INSTANCES_FILE}")
fi

if [[ -n "${CHECKPOINT_EVERY:-}" ]]; then
  CMD+=(--checkpoint_every "${CHECKPOINT_EVERY}")
fi

echo "=== Command ==="
printf '%q ' "${CMD[@]}"
echo

"${CMD[@]}"

EXIT=$?
date
echo "=== Exit: ${EXIT} ==="
echo "=== Results in ${OUT_ROOT} ==="
ls -la "${OUT_ROOT}"
print_storage_snapshot "after RM eval"
exit "${EXIT}"
