#!/bin/bash

# Shared Apptainer/Singularity helpers for Bridges2 LLM jobs.
# Source after loading modules on the host.

source /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/bridges2_sbatch_under_review/psc_ocean_env.sh

export BDI_APPTAINER_IMG="${BDI_APPTAINER_IMG:-/ocean/containers/ngc/pytorch/pytorch_25.02-py3.sif}"
export BDI_APPTAINER_ROOT="${BDI_APPTAINER_ROOT:-${BDI_PROJECT_ROOT}/apptainer}"
export BDI_APPTAINER_CACHE="${BDI_APPTAINER_CACHE:-${BDI_APPTAINER_ROOT}/cache}"
export BDI_APPTAINER_TMPDIR="${BDI_APPTAINER_TMPDIR:-${BDI_APPTAINER_ROOT}/tmp}"
export BDI_APPTAINER_ENV_ROOT="${BDI_APPTAINER_ENV_ROOT:-${BDI_APPTAINER_ROOT}/envs}"
export BDI_APPTAINER_VENV="${BDI_APPTAINER_VENV:-${BDI_APPTAINER_ENV_ROOT}/glm47flash}"
export BDI_APPTAINER_LOG_ROOT="${BDI_APPTAINER_LOG_ROOT:-${BDI_LOG_ROOT}/apptainer}"
export BDI_VLLM_PRECOMPILED_WHEEL_VARIANT="${BDI_VLLM_PRECOMPILED_WHEEL_VARIANT:-cu126}"

export APPTAINER_CACHEDIR="${BDI_APPTAINER_CACHE}"
export APPTAINER_TMPDIR="${BDI_APPTAINER_TMPDIR}"

mkdir -p \
  "${BDI_APPTAINER_ROOT}" \
  "${BDI_APPTAINER_CACHE}" \
  "${BDI_APPTAINER_TMPDIR}" \
  "${BDI_APPTAINER_ENV_ROOT}" \
  "${BDI_APPTAINER_LOG_ROOT}"

apptainer_host_binds() {
  printf '%s' \
    "${BDI_PROJECT_ROOT}:${BDI_PROJECT_ROOT},${BDI_REPO_ROOT}:${BDI_REPO_ROOT},${BDI_VENDOR_ROOT}:${BDI_VENDOR_ROOT},${BDI_APPTAINER_ROOT}:${BDI_APPTAINER_ROOT},${BDI_HF_HOME}:${BDI_HF_HOME},${BDI_HF_HUB_CACHE}:${BDI_HF_HUB_CACHE},${BDI_PIP_CACHE}:${BDI_PIP_CACHE},${BDI_TMP_ROOT}:${BDI_TMP_ROOT},${BDI_LOG_ROOT}:${BDI_LOG_ROOT},${BDI_RUN_ROOT}:${BDI_RUN_ROOT}"
}

apptainer_exec_bdi() {
  local inner_cmd="$1"
  APPTAINERENV_HF_HOME="${BDI_HF_HOME}" \
  APPTAINERENV_HF_HUB_CACHE="${BDI_HF_HUB_CACHE}" \
  APPTAINERENV_HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER}" \
  APPTAINERENV_TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE}" \
  APPTAINERENV_HF_DATASETS_OFFLINE="${HF_DATASETS_OFFLINE}" \
  APPTAINERENV_PIP_CACHE_DIR="${BDI_PIP_CACHE}" \
  APPTAINERENV_TMPDIR="${BDI_TMP_ROOT}" \
  APPTAINERENV_PYTHONNOUSERSITE="1" \
  APPTAINERENV_OPENAI_API_KEY="${OPENAI_API_KEY}" \
  apptainer exec --nv --cleanenv --writable-tmpfs \
    --bind "$(apptainer_host_binds)" \
    "${BDI_APPTAINER_IMG}" \
    bash -lc "set -euo pipefail
mkdir -p /usr/local/cuda/compat
if [[ ! -e /usr/local/cuda/compat/lib && -d /usr/local/cuda-12.8/compat/lib.real ]]; then
  ln -s /usr/local/cuda-12.8/compat/lib.real /usr/local/cuda/compat/lib
fi
export LD_LIBRARY_PATH=/usr/local/cuda/compat/lib:\${LD_LIBRARY_PATH:-}
${inner_cmd}"
}
