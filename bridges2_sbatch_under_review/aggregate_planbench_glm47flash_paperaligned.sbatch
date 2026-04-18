#!/bin/bash
#SBATCH --job-name=glm47_pb_agg
#SBATCH --account=cis260113p
#SBATCH --partition=RM-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=/ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/glm47_pb_agg_%j.out
#SBATCH --error=/ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/glm47_pb_agg_%j.err

set -euo pipefail

module purge
module load anaconda3/2024.10-1
source /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/bridges2_sbatch_under_review/psc_ocean_env.sh

set -a
source "${BDI_REPO_ROOT}/bridges2_sbatch_under_review/bdi_env.env"
set +a

RUN_TAG="${RUN_TAG:-glm47flash_eval_$(date +%Y%m%d)}"
RESULTS_ROOT="${BDI_RUN_ROOT}/${RUN_TAG}"
TABLE_OUT="${BDI_TABLE_ROOT}/${RUN_TAG}"

mkdir -p "${TABLE_OUT}"

export PYTHONPATH="${BDI_REPO_ROOT}:${PYTHONPATH:-}"

echo "=== Aggregate PlanBench tables ==="
echo "Run tag: ${RUN_TAG}"
echo "Results root: ${RESULTS_ROOT}"
echo "Table output: ${TABLE_OUT}"
date

cd "${BDI_REPO_ROOT}"
python scripts/evaluation/aggregate_planbench_paper_tables.py \
  --results_root "${RESULTS_ROOT}" \
  --output_dir "${TABLE_OUT}"

EXIT=$?
date
echo "=== Exit: ${EXIT} ==="
ls -la "${TABLE_OUT}"
exit "${EXIT}"
