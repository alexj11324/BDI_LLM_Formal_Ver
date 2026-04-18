#!/bin/bash
#SBATCH --job-name=qwen36_tp_val
#SBATCH --account=cis260113p
#SBATCH --partition=RM-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=15G
#SBATCH --time=08:00:00
#SBATCH --output=/ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/qwen36_tp_val_%j.out
#SBATCH --error=/ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/qwen36_tp_val_%j.err

set -euo pipefail

module purge
module load anaconda3/2024.10-1
source /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/bridges2_sbatch_under_review/psc_ocean_env.sh

set -a
source "${BDI_REPO_ROOT}/bridges2_sbatch_under_review/bdi_env.env"
set +a

if [[ ! -f "${BDI_SERVICE_READY_ENV_FILE}" ]]; then
  echo "Missing GPU service ready env: ${BDI_SERVICE_READY_ENV_FILE}" >&2
  echo "Start scripts/psc_deploy/serve_qwen36_mtp.sbatch first and write the ready_env file." >&2
  exit 1
fi

set -a
source "${BDI_SERVICE_READY_ENV_FILE}"
set +a

: "${VLLM_HOST:?VLLM_HOST missing from service ready env}"
: "${VLLM_PORT:?VLLM_PORT missing from service ready env}"
: "${OPENAI_API_BASE:?OPENAI_API_BASE missing from service ready env}"

export TRAVELPLANNER_HOME="${BDI_PROJECT_ROOT}/TravelPlanner_official"
export TRAVELPLANNER_BDI_PROMPT_VERSION="${TRAVELPLANNER_BDI_PROMPT_VERSION:-v3}"
export LLM_ENABLE_THINKING="true"
export LLM_TIMEOUT="${LLM_TIMEOUT:-900}"

if [ ! -d "${TRAVELPLANNER_HOME}/evaluation" ] || [ ! -f "${TRAVELPLANNER_HOME}/evaluation/eval.py" ]; then
  echo "ERROR: TRAVELPLANNER_HOME=${TRAVELPLANNER_HOME} is not a valid TravelPlanner checkout." >&2
  exit 1
fi

RUN_TAG="${RUN_TAG:-qwen36_tp_val_$(date +%Y%m%d_%H%M)}"
WORKERS="${WORKERS:-4}"
OPENAI_MODELS_URL="${OPENAI_API_BASE}/models"

mkdir -p "${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner"

export OPENAI_API_KEY="${OPENAI_API_KEY:-EMPTY}"
export LLM_MODEL="${LLM_MODEL:-openai/qwen3.6-35b-a3b}"
export SAVE_REASONING_TRACE="${SAVE_REASONING_TRACE:-1}"
export REASONING_TRACE_MAX_CHARS="${REASONING_TRACE_MAX_CHARS:-20000}"
export USER_SITE=/ocean/projects/cis260113p/zjiang9/python_user/lib/python3.12/site-packages
export PYTHONPATH="${BDI_REPO_ROOT}:${USER_SITE}:${PYTHONPATH:-}"

echo "=== RM TravelPlanner validation evaluation (Qwen3.6) ==="
echo "Node: $(hostname)"
echo "Run tag: ${RUN_TAG}"
echo "Workers: ${WORKERS}"
echo "OPENAI_API_BASE=${OPENAI_API_BASE}"
echo "LLM_MODEL=${LLM_MODEL}"
echo "LLM_ENABLE_THINKING=${LLM_ENABLE_THINKING}"
date

wait_for_openai_compat "${OPENAI_MODELS_URL}" 120
curl -fsS "${OPENAI_MODELS_URL}"

cd "${BDI_REPO_ROOT}"

python scripts/evaluation/run_travelplanner_release_matrix.py \
  --run-validation \
  --workers "${WORKERS}" \
  --travelplanner-home "${TRAVELPLANNER_HOME}" \
  --output-dir "${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner" \
  --timeout-seconds 25200

EXIT=$?
date
echo "=== Exit: ${EXIT} ==="
ls -la "${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner"
exit "${EXIT}"
