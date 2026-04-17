#!/bin/bash
#SBATCH --job-name=eval_glm47_appt
#SBATCH --account=cis260113p
#SBATCH --partition=GPU-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:h100-80:1
#SBATCH --mem=120G
#SBATCH --time=02:00:00
#SBATCH --output=/ocean/projects/cis260113p/zjiang9/logs/slurm/eval_glm47_appt_%j.out
#SBATCH --error=/ocean/projects/cis260113p/zjiang9/logs/slurm/eval_glm47_appt_%j.err

module purge
module load anaconda3/2024.10-1
source /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/bridges2_sbatch_under_review/psc_apptainer_env.sh

set -a
source "${BDI_REPO_ROOT}/bridges2_sbatch_under_review/bdi_env.env"
set +a

VLLM_HOST="${VLLM_HOST:-127.0.0.1}"
VLLM_PORT="${VLLM_PORT:-8000}"
OPENAI_MODELS_URL="http://${VLLM_HOST}:${VLLM_PORT}/v1/models"
SERVICE_LOG="${BDI_APPTAINER_LOG_ROOT}/glm47flash_eval_apptainer_${SLURM_JOB_ID:-manual}.log"
OUT="${BDI_RUN_ROOT}/glm_4_7_flash_appt_eval_$(date +%Y%m%d_%H%M%S)"
DOMAIN="${DOMAIN:-blocksworld}"
MAX_INSTANCES="${MAX_INSTANCES:-10}"
WORKERS="${WORKERS:-1}"
VLLM_PID=""
PREFLIGHT_PY="${BDI_TMP_ROOT}/run_eval_glm47flash_apptainer_preflight.py"

cleanup_vllm() {
  cleanup_pid_if_running "${VLLM_PID:-}"
}

trap cleanup_vllm EXIT

if [[ ! -f "${BDI_APPTAINER_VENV}/pyvenv.cfg" ]]; then
  echo "Missing container venv at ${BDI_APPTAINER_VENV}. Run install_glm47flash_apptainer.sbatch first." >&2
  exit 1
fi

cat > "${PREFLIGHT_PY}" <<'PY'
import platform
import torch
import vllm
import transformers
import triton

print("glibc", platform.libc_ver())
print("torch", torch.__version__)
print("torch_cuda", torch.version.cuda)
print("cuda_available", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device_name", torch.cuda.get_device_name(0))
print("vllm", vllm.__version__)
print("transformers", transformers.__version__)
print("triton", triton.__version__)
PY

export LLM_MODEL="openai/zai-org/GLM-4.7-Flash"
export OPENAI_API_BASE="http://${VLLM_HOST}:${VLLM_PORT}/v1"
export SAVE_REASONING_TRACE="${SAVE_REASONING_TRACE:-1}"
export REASONING_TRACE_MAX_CHARS="${REASONING_TRACE_MAX_CHARS:-20000}"
export VLLM_USE_FLASHINFER_MOE_FP16="${VLLM_USE_FLASHINFER_MOE_FP16:-0}"
export PYTHONPATH="${BDI_REPO_ROOT}:${BDI_REPO_ROOT}/src:${PYTHONPATH:-}"

mkdir -p "${OUT}"

echo "=== Host node ==="
hostname
date
echo "Container image: ${BDI_APPTAINER_IMG}"
echo "Container venv: ${BDI_APPTAINER_VENV}"
print_storage_snapshot "before apptainer eval"
nvidia-smi || true

echo
echo "=== Container preflight ==="
apptainer_exec_bdi "
source '${BDI_APPTAINER_VENV}/bin/activate'
export VLLM_USE_FLASHINFER_MOE_FP16='${VLLM_USE_FLASHINFER_MOE_FP16}'
export PYTHONPATH='${PYTHONPATH}'
python '${PREFLIGHT_PY}'
"

echo
echo "=== Starting vLLM in Apptainer ==="
: > "${SERVICE_LOG}"
apptainer_exec_bdi "
source '${BDI_APPTAINER_VENV}/bin/activate'
export OPENAI_API_KEY='${OPENAI_API_KEY}'
export HF_HOME='${BDI_HF_HOME}'
export HF_HUB_CACHE='${BDI_HF_HUB_CACHE}'
export VLLM_USE_FLASHINFER_MOE_FP16='${VLLM_USE_FLASHINFER_MOE_FP16}'
export PYTHONPATH='${PYTHONPATH}'
vllm serve '${BDI_MODEL_REPO}' --host '${VLLM_HOST}' --port '${VLLM_PORT}'
" > "${SERVICE_LOG}" 2>&1 &
VLLM_PID=$!

wait_for_openai_compat "${OPENAI_MODELS_URL}" 600 "${SERVICE_LOG}" "${VLLM_PID}"
curl -fsS "${OPENAI_MODELS_URL}"

echo
echo "=== Run verification-only evaluation in Apptainer ==="
apptainer_exec_bdi "
source '${BDI_APPTAINER_VENV}/bin/activate'
export OPENAI_API_BASE='${OPENAI_API_BASE}'
export OPENAI_API_KEY='${OPENAI_API_KEY}'
export LLM_MODEL='${LLM_MODEL}'
export SAVE_REASONING_TRACE='${SAVE_REASONING_TRACE}'
export REASONING_TRACE_MAX_CHARS='${REASONING_TRACE_MAX_CHARS}'
export VLLM_USE_FLASHINFER_MOE_FP16='${VLLM_USE_FLASHINFER_MOE_FP16}'
export PYTHONPATH='${PYTHONPATH}'
cd '${BDI_REPO_ROOT}'
python scripts/evaluation/run_verification_only.py \
  --domain '${DOMAIN}' \
  --max_instances '${MAX_INSTANCES}' \
  --workers '${WORKERS}' \
  --output_dir '${OUT}'
"

EXIT=$?
date
echo "=== Exit: ${EXIT} ==="
echo "=== Results in ${OUT} ==="
ls -la "${OUT}"
echo "=== Service log: ${SERVICE_LOG} ==="
tail -n 120 "${SERVICE_LOG}" || true
print_storage_snapshot "after apptainer eval"
exit "${EXIT}"
