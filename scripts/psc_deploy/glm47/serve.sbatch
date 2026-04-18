#!/bin/bash
#SBATCH -J glm47_serve_mtp
#SBATCH -A cis260113p
#SBATCH -p GPU-shared
#SBATCH --gres=gpu:h100-80:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH -t 04:00:00
#SBATCH -o /ocean/projects/cis250019p/zjiang9/serve_mtp_%j.out
#SBATCH -e /ocean/projects/cis250019p/zjiang9/serve_mtp_%j.err

set -eu
echo "===== node=$(hostname) job=$SLURM_JOB_ID start=$(date) ====="
exec bash /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/scripts/psc_deploy/glm47/run_vllm.sh
