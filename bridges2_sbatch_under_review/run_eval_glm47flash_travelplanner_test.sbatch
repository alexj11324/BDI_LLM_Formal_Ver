#!/bin/bash
#SBATCH --job-name=glm47_tp_test
#SBATCH --account=cis260113p
#SBATCH --partition=RM-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --time=12:00:00
#SBATCH --output=/ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/glm47_tp_test_%j.out
#SBATCH --error=/ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/glm47_tp_test_%j.err

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

export TRAVELPLANNER_HOME="${BDI_PROJECT_ROOT}/TravelPlanner_official"
export TRAVELPLANNER_BDI_PROMPT_VERSION="${TRAVELPLANNER_BDI_PROMPT_VERSION:-v3}"
export LLM_ENABLE_THINKING="false"   # override bdi_env.env for TravelPlanner
export LLM_TIMEOUT="${LLM_TIMEOUT:-900}"  # TravelPlanner itineraries are longer

if [ ! -d "${TRAVELPLANNER_HOME}/evaluation" ] || [ ! -f "${TRAVELPLANNER_HOME}/evaluation/eval.py" ]; then
  echo "ERROR: TRAVELPLANNER_HOME=${TRAVELPLANNER_HOME} is not a valid TravelPlanner checkout." >&2
  echo "Run setup_travelplanner_deps.sbatch first." >&2
  exit 1
fi

RUN_TAG="${RUN_TAG:-glm47flash_tp_test_$(date +%Y%m%d)}"
WORKERS="${WORKERS:-16}"
OPENAI_MODELS_URL="${OPENAI_API_BASE}/models"

mkdir -p "${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner_test"

export OPENAI_API_KEY="${OPENAI_API_KEY:-EMPTY}"
export LLM_MODEL="${LLM_MODEL:-openai/glm47flash}"
export SAVE_REASONING_TRACE="${SAVE_REASONING_TRACE:-1}"
export REASONING_TRACE_MAX_CHARS="${REASONING_TRACE_MAX_CHARS:-20000}"
export PYTHONPATH="${BDI_REPO_ROOT}:${PYTHONPATH:-}"

echo "=== RM TravelPlanner test evaluation ==="
echo "Node: $(hostname)"
echo "Run tag: ${RUN_TAG}"
echo "Workers: ${WORKERS}"
echo "TravelPlanner home: ${TRAVELPLANNER_HOME}"
echo "Output dir: ${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner_test"
echo "Service env: ${BDI_SERVICE_READY_ENV_FILE}"
echo "Service manifest: ${SERVER_MANIFEST_PATH}"
echo "OPENAI_API_BASE=${OPENAI_API_BASE}"
echo "TRAVELPLANNER_BDI_PROMPT_VERSION=${TRAVELPLANNER_BDI_PROMPT_VERSION}"
echo "LLM_ENABLE_THINKING=${LLM_ENABLE_THINKING}"
echo "LLM_TIMEOUT=${LLM_TIMEOUT}"
date
print_storage_snapshot "before RM TravelPlanner test eval"

wait_for_openai_compat "${OPENAI_MODELS_URL}" 120
curl -fsS "${OPENAI_MODELS_URL}"

cd "${BDI_REPO_ROOT}"

CMD=(
  python scripts/evaluation/run_travelplanner_release_matrix.py
  --run-test
  --workers "${WORKERS}"
  --travelplanner-home "${TRAVELPLANNER_HOME}"
  --output-dir "${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner_test"
  --hf-token-env HF_TOKEN
  --timeout-seconds 39600
)

echo "=== Command ==="
printf '%q ' "${CMD[@]}"
echo

"${CMD[@]}"

EXIT=$?
date
echo "=== Exit: ${EXIT} ==="
echo "=== Results in ${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner_test ==="
ls -la "${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner_test"
print_storage_snapshot "after RM TravelPlanner test eval"
exit "${EXIT}"
