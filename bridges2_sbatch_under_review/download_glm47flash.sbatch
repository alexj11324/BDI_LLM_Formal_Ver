#!/bin/bash
#SBATCH --job-name=dl_glm47f
#SBATCH --account=cis260113p
#SBATCH --partition=GPU-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:v100-16:1
#SBATCH --mem=20G
#SBATCH --time=00:30:00
#SBATCH --output=/ocean/projects/cis260113p/zjiang9/logs/slurm/dl_glm47f_%j.out

module purge
module load anaconda3/2024.10-1
source /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/bridges2_sbatch_under_review/psc_ocean_env.sh

echo "=== Node: $(hostname) ==="
date
print_storage_snapshot "before model download"

python3 << 'PYEOF'
from huggingface_hub import snapshot_download
import os
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
path = snapshot_download(
    repo_id="zai-org/GLM-4.7-Flash",
    cache_dir="/ocean/projects/cis260113p/zjiang9/hf_cache/hub",
    max_workers=16,
)
print(f"Downloaded to: {path}")
PYEOF

date
du -sh /ocean/projects/cis260113p/zjiang9/hf_cache/hub/models--zai-org--GLM-4.7-Flash 2>/dev/null
print_storage_snapshot "after model download"
