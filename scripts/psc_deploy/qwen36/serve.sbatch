#!/bin/bash
#SBATCH -J qwen36_serve_mtp
#SBATCH -A cis260113p
#SBATCH -p GPU-shared
#SBATCH --gres=gpu:h100-80:4
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=32
#SBATCH --mem=240G
#SBATCH -t 04:00:00
#SBATCH -o /ocean/projects/cis250019p/zjiang9/qwen36_serve_%j.out
#SBATCH -e /ocean/projects/cis250019p/zjiang9/qwen36_serve_%j.err

set -eu
echo "===== node=$(hostname) job=$SLURM_JOB_ID start=$(date) ====="
exec bash /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/scripts/psc_deploy/qwen36/run_vllm.sh
