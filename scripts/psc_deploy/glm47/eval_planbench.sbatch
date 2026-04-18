#!/bin/bash
#SBATCH -J glm47_planbench
#SBATCH -A cis260113p
#SBATCH -p RM-shared
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=15G
#SBATCH -t 08:00:00
#SBATCH -o /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/glm47_planbench_%j.out
#SBATCH -e /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/glm47_planbench_%j.err

set -euo pipefail
module purge
module load anaconda3/2024.10-1
source /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/bridges2_sbatch_under_review/psc_ocean_env.sh

set -a
source "${BDI_REPO_ROOT}/bridges2_sbatch_under_review/bdi_env.env"
source "${BDI_SERVICE_READY_ENV_FILE}"
set +a

: "${OPENAI_API_BASE:?OPENAI_API_BASE missing from ready env}"

export USER_SITE=/ocean/projects/cis260113p/zjiang9/python_user/lib/python3.12/site-packages
export PYTHONPATH="${BDI_REPO_ROOT}:${USER_SITE}:${PYTHONPATH:-}"
export LLM_MODEL="${LLM_MODEL:-openai/glm-4.7-flash}"
export LLM_ENABLE_THINKING="true"
export OPENAI_API_KEY="${OPENAI_API_KEY:-EMPTY}"
export LLM_TIMEOUT="${LLM_TIMEOUT:-900}"

RUN_TAG="${RUN_TAG:-glm47flash_planbench_apialign_$(date +%H%M)}"
WORKERS="${WORKERS:-4}"
OUT_DIR="${BDI_RUN_ROOT}/${RUN_TAG}/planbench"
mkdir -p "${OUT_DIR}"

echo "=== PlanBench paperaligned evaluation ==="
echo "Node: $(hostname)"
echo "Run tag: ${RUN_TAG}"
echo "OPENAI_API_BASE=${OPENAI_API_BASE}"
echo "LLM_MODEL=${LLM_MODEL}"
echo "Workers: ${WORKERS}"
echo "Output: ${OUT_DIR}"
date

cd "${BDI_REPO_ROOT}"
python scripts/evaluation/run_planbench_paperaligned.py \
  --all_domains \
  --parallel \
  --workers "${WORKERS}" \
  --execution_mode bdi-repair \
  --max_instances 100 \
  --output_dir "${OUT_DIR}" \
  --manifest_out "${OUT_DIR}/manifest.json"

date
echo "=== Exit $? ==="
