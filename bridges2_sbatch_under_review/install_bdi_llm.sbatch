#!/bin/bash
#SBATCH --job-name=inst_bdi
#SBATCH --account=cis260113p
#SBATCH --partition=RM-shared
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem-per-cpu=2000M
#SBATCH --time=00:20:00
#SBATCH --output=/ocean/projects/cis260113p/zjiang9/logs/slurm/inst_bdi_%j.out
#SBATCH --error=/ocean/projects/cis260113p/zjiang9/logs/slurm/inst_bdi_%j.err

module purge
module load anaconda3/2024.10-1
source /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/bridges2_sbatch_under_review/psc_ocean_env.sh

ENV_KIND="${ENV_KIND:-stable}"
ENV_PREFIX="$(select_vllm_env_prefix "${ENV_KIND}")"

print_storage_snapshot "before install (${ENV_KIND})"

echo "=== Install target ==="
echo "ENV_KIND=${ENV_KIND}"
echo "ENV_PREFIX=${ENV_PREFIX}"
echo "REPO=${BDI_REPO_ROOT}"
date

if [[ ! -d "${BDI_REPO_ROOT}" ]]; then
  echo "Missing repo at ${BDI_REPO_ROOT}" >&2
  exit 1
fi

echo
echo "=== Recreate clean conda env ==="
rm -rf "${ENV_PREFIX}"
conda create --yes --prefix "${ENV_PREFIX}" python=3.11
activate_conda_prefix "${ENV_PREFIX}"

echo
echo "=== Upgrade packaging toolchain ==="
python -m pip install --upgrade pip setuptools wheel

echo
echo "=== Install vLLM (${ENV_KIND}) ==="
if [[ "${ENV_KIND}" == "stable" ]]; then
  python -m pip install "vllm==${BDI_VLLM_STABLE_VERSION}" \
    --extra-index-url "${BDI_TORCH_WHEEL_INDEX}"
else
  python -m pip install --upgrade --only-binary=:all: vllm --pre \
    --index-url "${BDI_PYPI_INDEX_URL}" \
    --extra-index-url "${BDI_VLLM_NIGHTLY_INDEX}"
  echo
  echo "=== Install transformers main branch for GLM-4.7-Flash ==="
  python -m pip install --upgrade "${BDI_TRANSFORMERS_GIT_URL}"
fi

echo
echo "=== Install bdi_llm editable package ==="
cd "${BDI_REPO_ROOT}"
python -m pip install -e ".[dev]"

echo
echo "=== Verify Python imports ==="
python - <<'PY'
import bdi_llm
import dspy
import torch
import transformers

print("bdi_llm imported successfully")
print(f"dspy.__version__: {dspy.__version__}")
print(f"torch.__version__: {torch.__version__}")
print(f"transformers.__version__: {transformers.__version__}")
PY

echo
echo "=== Triton diagnostics ==="
log_triton_diagnostics

echo
print_storage_snapshot "after install (${ENV_KIND})"
date
