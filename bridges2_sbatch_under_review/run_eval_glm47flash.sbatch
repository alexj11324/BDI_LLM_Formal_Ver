#!/bin/bash
#SBATCH --job-name=eval_glm47f
#SBATCH --account=cis260113p
#SBATCH --partition=GPU-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:h100-80:1
#SBATCH --mem=120G
#SBATCH --time=02:00:00
#SBATCH --output=/ocean/projects/cis260113p/zjiang9/logs/slurm/eval_%j.out
#SBATCH --error=/ocean/projects/cis260113p/zjiang9/logs/slurm/eval_%j.err

module purge
module load anaconda3/2024.10-1
source /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/bridges2_sbatch_under_review/psc_ocean_env.sh

set -a
source "${BDI_REPO_ROOT}/bridges2_sbatch_under_review/bdi_env.env"
set +a

if [[ -f "${BDI_READY_ENV_FILE}" ]]; then
  source "${BDI_READY_ENV_FILE}"
fi

ENV_KIND="${BDI_SELECTED_VLLM_ENV_KIND:-${ENV_KIND:-stable}}"
ENV_PREFIX="${BDI_SELECTED_VLLM_ENV_PREFIX:-$(select_vllm_env_prefix "${ENV_KIND}")}"
VLLM_HOST="${VLLM_HOST:-127.0.0.1}"
VLLM_PORT="${VLLM_PORT:-8000}"
OPENAI_MODELS_URL="http://${VLLM_HOST}:${VLLM_PORT}/v1/models"
SERVICE_LOG="${BDI_SERVICE_LOG_ROOT}/glm47flash_eval_${ENV_KIND}_${SLURM_JOB_ID:-manual}.log"
OUT="${BDI_RUN_ROOT}/glm_4_7_flash_eval_$(date +%Y%m%d_%H%M%S)"
DOMAIN="${DOMAIN:-blocksworld}"
MAX_INSTANCES="${MAX_INSTANCES:-10}"
WORKERS="${WORKERS:-1}"
VLLM_PID=""

cleanup_vllm() {
  cleanup_pid_if_running "${VLLM_PID:-}"
}

trap cleanup_vllm EXIT

if [[ ! -d "${ENV_PREFIX}" ]]; then
  echo "Missing vLLM env at ${ENV_PREFIX}. Run install_bdi_llm.sbatch first." >&2
  exit 1
fi

activate_conda_prefix "${ENV_PREFIX}"

export LLM_MODEL="openai/zai-org/GLM-4.7-Flash"
export OPENAI_API_BASE="http://${VLLM_HOST}:${VLLM_PORT}/v1"
export SAVE_REASONING_TRACE="${SAVE_REASONING_TRACE:-1}"
export REASONING_TRACE_MAX_CHARS="${REASONING_TRACE_MAX_CHARS:-20000}"
export PYTHONPATH="${BDI_REPO_ROOT}:${PYTHONPATH:-}"

mkdir -p "${OUT}"

echo "=== Node: $(hostname) ==="
echo "ENV_KIND=${ENV_KIND}"
echo "ENV_PREFIX=${ENV_PREFIX}"
echo "Output dir: ${OUT}"
date
print_storage_snapshot "before eval (${ENV_KIND})"
python -c "import torch; print('cuda avail:', torch.cuda.is_available(), 'device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"

echo
echo "=== Preflight diagnostics ==="
log_triton_diagnostics

echo
echo "=== Starting vLLM serve ==="
: > "${SERVICE_LOG}"
vllm serve "${BDI_MODEL_REPO}" \
  --host "${VLLM_HOST}" \
  --port "${VLLM_PORT}" \
  > "${SERVICE_LOG}" 2>&1 &
VLLM_PID=$!

wait_for_openai_compat "${OPENAI_MODELS_URL}" 600 "${SERVICE_LOG}" "${VLLM_PID}"
curl -fsS "${OPENAI_MODELS_URL}"

echo
echo "=== Run verification-only evaluation ==="
cd "${BDI_REPO_ROOT}"
python scripts/evaluation/run_verification_only.py \
  --domain "${DOMAIN}" \
  --max_instances "${MAX_INSTANCES}" \
  --workers "${WORKERS}" \
  --output_dir "${OUT}"

EXIT=$?
date
echo "=== Exit: ${EXIT} ==="
echo "=== Results in ${OUT} ==="
ls -la "${OUT}"
echo "=== Service log: ${SERVICE_LOG} ==="
tail -n 80 "${SERVICE_LOG}" || true
print_storage_snapshot "after eval (${ENV_KIND})"
exit "${EXIT}"
