#!/bin/bash
#SBATCH --job-name=glm47_tp_agg
#SBATCH --account=cis260113p
#SBATCH --partition=RM-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:30:00
#SBATCH --output=/ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/glm47_tp_agg_%j.out
#SBATCH --error=/ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/glm47_tp_agg_%j.err

set -euo pipefail

module purge
module load anaconda3/2024.10-1
source /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/bridges2_sbatch_under_review/psc_ocean_env.sh

set -a
source "${BDI_REPO_ROOT}/bridges2_sbatch_under_review/bdi_env.env"
set +a

export PYTHONPATH="${BDI_REPO_ROOT}:${PYTHONPATH:-}"

cd "${BDI_REPO_ROOT}"

: "${RUN_TAG:?RUN_TAG is required — pass via --export=RUN_TAG=<value> to sbatch}"

if [[ ! -d "${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner/validation/" ]]; then
  echo "ERROR: Results directory not found: ${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner/validation/" >&2
  echo "Run run_eval_glm47flash_travelplanner.sbatch (with RUN_TAG=${RUN_TAG}) first and wait for it to complete." >&2
  exit 1
fi

echo "=== Aggregate TravelPlanner paper-aligned tables ==="
echo "Run tag: ${RUN_TAG}"
echo "Results root: ${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner"
echo "Table output: ${BDI_TABLE_ROOT}/${RUN_TAG}/travelplanner"
date

mkdir -p "${BDI_TABLE_ROOT}/${RUN_TAG}/travelplanner"

CMD=(python scripts/evaluation/aggregate_travelplanner_paper_tables.py
     --results_root "${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner"
     --output_dir "${BDI_TABLE_ROOT}/${RUN_TAG}/travelplanner"
     --run-tag "${RUN_TAG}")

printf '%q ' "${CMD[@]}"; echo
"${CMD[@]}"

date
ls -la "${BDI_TABLE_ROOT}/${RUN_TAG}/travelplanner"
