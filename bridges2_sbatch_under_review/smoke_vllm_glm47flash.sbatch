#!/bin/bash
#SBATCH --job-name=smoke_glm47f
#SBATCH --account=cis260113p
#SBATCH --partition=GPU-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:h100-80:1
#SBATCH --mem=120G
#SBATCH --time=01:00:00
#SBATCH --output=/ocean/projects/cis260113p/zjiang9/logs/slurm/smoke_glm47f_%j.out
#SBATCH --error=/ocean/projects/cis260113p/zjiang9/logs/slurm/smoke_glm47f_%j.err

module purge
module load anaconda3/2024.10-1
source /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/bridges2_sbatch_under_review/psc_ocean_env.sh

set -a
source "${BDI_REPO_ROOT}/bridges2_sbatch_under_review/bdi_env.env"
set +a

VLLM_HOST="${VLLM_HOST:-127.0.0.1}"
VLLM_PORT="${VLLM_PORT:-8000}"
OPENAI_MODELS_URL="http://${VLLM_HOST}:${VLLM_PORT}/v1/models"
READY_TIMEOUT_SECONDS="${READY_TIMEOUT_SECONDS:-600}"
AUTO_FALLBACK_TO_NIGHTLY="${AUTO_FALLBACK_TO_NIGHTLY:-1}"
ACTIVE_SERVICE_LOG=""
VLLM_PID=""

cleanup_vllm() {
  cleanup_pid_if_running "${VLLM_PID:-}"
}

trap cleanup_vllm EXIT

run_smoke_once() {
  local env_kind="$1"
  local env_prefix
  env_prefix="$(select_vllm_env_prefix "${env_kind}")"
  ACTIVE_SERVICE_LOG="${BDI_SERVICE_LOG_ROOT}/glm47flash_smoke_${env_kind}_${SLURM_JOB_ID:-manual}.log"
  : > "${ACTIVE_SERVICE_LOG}"

  echo "=== Smoke target (${env_kind}) ===" | tee -a "${ACTIVE_SERVICE_LOG}"
  echo "ENV_PREFIX=${env_prefix}" | tee -a "${ACTIVE_SERVICE_LOG}"

  if [[ ! -d "${env_prefix}" ]]; then
    echo "Missing env at ${env_prefix}. Run install_bdi_llm.sbatch first." | tee -a "${ACTIVE_SERVICE_LOG}" >&2
    return 2
  fi

  activate_conda_prefix "${env_prefix}"
  export PYTHONPATH="${BDI_REPO_ROOT}:${PYTHONPATH:-}"

  {
    echo "=== Node: $(hostname) ==="
    date
    print_storage_snapshot "before smoke (${env_kind})"
    python -c "import torch; print('cuda avail:', torch.cuda.is_available(), 'device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"
    echo "=== Preflight diagnostics ==="
    log_triton_diagnostics
  } >> "${ACTIVE_SERVICE_LOG}" 2>&1

  {
    echo "=== Starting vLLM serve (${env_kind}) ==="
    vllm serve "${BDI_MODEL_REPO}" \
      --host "${VLLM_HOST}" \
      --port "${VLLM_PORT}"
  } >> "${ACTIVE_SERVICE_LOG}" 2>&1 &
  VLLM_PID=$!

  if wait_for_openai_compat "${OPENAI_MODELS_URL}" "${READY_TIMEOUT_SECONDS}" "${ACTIVE_SERVICE_LOG}" "${VLLM_PID}"; then
    echo "=== READY (${env_kind}) ===" | tee -a "${ACTIVE_SERVICE_LOG}"
    curl -fsS "${OPENAI_MODELS_URL}" | tee -a "${ACTIVE_SERVICE_LOG}"
    write_ready_env_file "${env_kind}"
    cleanup_vllm
    VLLM_PID=""
    print_storage_snapshot "after smoke (${env_kind})" | tee -a "${ACTIVE_SERVICE_LOG}"
    return 0
  else
    local rc=$?
  echo "=== Smoke failed (${env_kind}) ===" | tee -a "${ACTIVE_SERVICE_LOG}"
  tail -n 120 "${ACTIVE_SERVICE_LOG}" || true
  cleanup_vllm
  VLLM_PID=""
  return "${rc}"
  fi
}

echo "=== Starting GLM-4.7-Flash smoke ==="
print_storage_snapshot "smoke entry"

if run_smoke_once stable; then
  exit 0
fi

STABLE_RC=$?
if [[ "${AUTO_FALLBACK_TO_NIGHTLY}" != "1" ]]; then
  exit "${STABLE_RC}"
fi

if ! is_known_triton_failure "${ACTIVE_SERVICE_LOG}"; then
  echo "Stable smoke failed without a known triton/vllm compatibility signature." >&2
  exit "${STABLE_RC}"
fi

echo "=== Stable smoke hit known Triton/vLLM issue; rebuilding nightly env ==="
ENV_KIND=nightly bash "${BDI_REPO_ROOT}/bridges2_sbatch_under_review/install_bdi_llm.sbatch"

run_smoke_once nightly
