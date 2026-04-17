#!/bin/bash
#SBATCH --job-name=inst_glm47_appt
#SBATCH --account=cis260113p
#SBATCH --partition=RM-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=6
#SBATCH --mem=24G
#SBATCH --time=00:45:00
#SBATCH --output=/ocean/projects/cis260113p/zjiang9/logs/slurm/inst_glm47_appt_%j.out
#SBATCH --error=/ocean/projects/cis260113p/zjiang9/logs/slurm/inst_glm47_appt_%j.err

module purge
module load anaconda3/2024.10-1
source /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/bridges2_sbatch_under_review/psc_apptainer_env.sh

print_storage_snapshot "before apptainer install"

echo "=== Apptainer image ==="
echo "${BDI_APPTAINER_IMG}"
date

if [[ ! -d "${BDI_VLLM_SRC_ROOT}/.git" ]]; then
  git clone https://github.com/vllm-project/vllm.git "${BDI_VLLM_SRC_ROOT}"
else
  git -C "${BDI_VLLM_SRC_ROOT}" fetch origin
fi
git -C "${BDI_VLLM_SRC_ROOT}" checkout origin/main

apptainer_exec_bdi "
set -euo pipefail
python -m venv '${BDI_APPTAINER_VENV}'
source '${BDI_APPTAINER_VENV}/bin/activate'
python -m pip install --upgrade pip setuptools wheel uv
uv pip install --python '${BDI_APPTAINER_VENV}/bin/python' \
  torch torchvision torchaudio \
  --index-url https://download.pytorch.org/whl/cu126
VLLM_USE_PRECOMPILED=1 \
VLLM_PRECOMPILED_WHEEL_COMMIT=nightly \
VLLM_PRECOMPILED_WHEEL_VARIANT='${BDI_VLLM_PRECOMPILED_WHEEL_VARIANT}' \
uv pip install --python '${BDI_APPTAINER_VENV}/bin/python' --editable '${BDI_VLLM_SRC_ROOT}'
python -m pip install --upgrade '${BDI_TRANSFORMERS_GIT_URL}'
python -m pip install -e '${BDI_REPO_ROOT}[dev]'
python - <<'\"'\"'PY'\"'\"'
import importlib
mods = ['vllm', 'torch', 'transformers', 'triton']
for name in mods:
    mod = importlib.import_module(name)
    print(name, getattr(mod, '__version__', 'unknown'))
PY
"

echo
print_storage_snapshot "after apptainer install"
date
