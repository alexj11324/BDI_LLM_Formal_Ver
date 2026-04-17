#!/bin/bash
#SBATCH --job-name=probe_glm47_appt
#SBATCH --account=cis260113p
#SBATCH --partition=GPU-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:h100-80:1
#SBATCH --mem=32G
#SBATCH --time=00:10:00
#SBATCH --output=/ocean/projects/cis260113p/zjiang9/logs/slurm/probe_glm47_appt_%j.out
#SBATCH --error=/ocean/projects/cis260113p/zjiang9/logs/slurm/probe_glm47_appt_%j.err

module purge
module load anaconda3/2024.10-1
source /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/bridges2_sbatch_under_review/psc_apptainer_env.sh

echo "=== Host snapshot ==="
date
hostname
print_storage_snapshot "before apptainer probe"
nvidia-smi || true

echo
echo "=== Container probe ==="
apptainer_exec_bdi '
python - <<'"'"'PY'"'"'
import platform
import sys
import torch

print("python", sys.version.split()[0])
print("glibc", platform.libc_ver())
print("torch", torch.__version__)
print("torch_cuda", torch.version.cuda)
print("cuda_available", torch.cuda.is_available())
print("device_count", torch.cuda.device_count())
if torch.cuda.is_available():
    print("device_name", torch.cuda.get_device_name(0))
PY
'

echo
echo "=== After probe ==="
print_storage_snapshot "after apptainer probe"
