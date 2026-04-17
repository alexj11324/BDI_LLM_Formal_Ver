#!/bin/bash

# Shared Bridges2 environment for BDI-LLM jobs.
# Source this file from sbatch scripts after loading the Anaconda module.

set -euo pipefail

export BDI_ACCOUNT="${BDI_ACCOUNT:-cis260113p}"
export BDI_PROJECT_ROOT="${BDI_PROJECT_ROOT:-/ocean/projects/${BDI_ACCOUNT}/zjiang9}"
export BDI_REPO_ROOT="${BDI_REPO_ROOT:-${BDI_PROJECT_ROOT}/repo/BDI_LLM_Formal_Ver}"
export BDI_ENV_ROOT="${BDI_ENV_ROOT:-${BDI_PROJECT_ROOT}/conda_envs}"
export BDI_CONDA_PKGS_DIR="${BDI_CONDA_PKGS_DIR:-${BDI_PROJECT_ROOT}/conda_pkgs}"
export BDI_PIP_CACHE="${BDI_PIP_CACHE:-${BDI_PROJECT_ROOT}/pip_cache}"
export BDI_TMP_ROOT="${BDI_TMP_ROOT:-${BDI_PROJECT_ROOT}/tmp}"
export BDI_PYTHONUSERBASE="${BDI_PYTHONUSERBASE:-${BDI_PROJECT_ROOT}/python_user}"
export BDI_HF_HOME="${BDI_HF_HOME:-${BDI_PROJECT_ROOT}/hf_cache}"
export BDI_HF_HUB_CACHE="${BDI_HF_HUB_CACHE:-${BDI_HF_HOME}/hub}"
export BDI_XDG_CACHE_HOME="${BDI_XDG_CACHE_HOME:-${BDI_PROJECT_ROOT}/xdg_cache}"
export BDI_LOG_ROOT="${BDI_LOG_ROOT:-${BDI_PROJECT_ROOT}/logs}"
export BDI_SLURM_LOG_ROOT="${BDI_SLURM_LOG_ROOT:-${BDI_LOG_ROOT}/slurm}"
export BDI_SERVICE_LOG_ROOT="${BDI_SERVICE_LOG_ROOT:-${BDI_LOG_ROOT}/services}"
export BDI_RUN_ROOT="${BDI_RUN_ROOT:-${BDI_PROJECT_ROOT}/runs}"
export BDI_STATUS_ROOT="${BDI_STATUS_ROOT:-${BDI_RUN_ROOT}/status}"
export BDI_VENDOR_ROOT="${BDI_VENDOR_ROOT:-${BDI_PROJECT_ROOT}/vendor}"
export BDI_VLLM_SRC_ROOT="${BDI_VLLM_SRC_ROOT:-${BDI_VENDOR_ROOT}/vllm-main}"
export BDI_MODEL_REPO="${BDI_MODEL_REPO:-zai-org/GLM-4.7-Flash}"
export BDI_VLLM_STABLE_ENV="${BDI_VLLM_STABLE_ENV:-${BDI_ENV_ROOT}/vllm_serve_clean}"
export BDI_VLLM_NIGHTLY_ENV="${BDI_VLLM_NIGHTLY_ENV:-${BDI_ENV_ROOT}/vllm_serve_nightly}"
export BDI_READY_ENV_FILE="${BDI_READY_ENV_FILE:-${BDI_STATUS_ROOT}/glm47flash_ready_env.sh}"
export BDI_TORCH_WHEEL_INDEX="${BDI_TORCH_WHEEL_INDEX:-https://download.pytorch.org/whl/cu128}"
export BDI_VLLM_STABLE_VERSION="${BDI_VLLM_STABLE_VERSION:-0.11.2}"
export BDI_VLLM_NIGHTLY_INDEX="${BDI_VLLM_NIGHTLY_INDEX:-https://wheels.vllm.ai/nightly}"
export BDI_PYPI_INDEX_URL="${BDI_PYPI_INDEX_URL:-https://pypi.org/simple}"
export BDI_TRANSFORMERS_GIT_URL="${BDI_TRANSFORMERS_GIT_URL:-git+https://github.com/huggingface/transformers.git}"

export TMPDIR="${BDI_TMP_ROOT}"
export PIP_CACHE_DIR="${BDI_PIP_CACHE}"
export PYTHONUSERBASE="${BDI_PYTHONUSERBASE}"
export PYTHONNOUSERSITE=1
export CONDA_PKGS_DIRS="${BDI_CONDA_PKGS_DIR}"
export HF_HOME="${BDI_HF_HOME}"
export HF_HUB_CACHE="${BDI_HF_HUB_CACHE}"
export XDG_CACHE_HOME="${BDI_XDG_CACHE_HOME}"
export HF_HUB_ENABLE_HF_TRANSFER="${HF_HUB_ENABLE_HF_TRANSFER:-1}"
export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
export HF_DATASETS_OFFLINE="${HF_DATASETS_OFFLINE:-1}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-EMPTY}"
export PATH="${PYTHONUSERBASE}/bin:${PATH}"

mkdir -p \
  "${BDI_ENV_ROOT}" \
  "${BDI_CONDA_PKGS_DIR}" \
  "${BDI_PIP_CACHE}" \
  "${BDI_TMP_ROOT}" \
  "${BDI_PYTHONUSERBASE}" \
  "${BDI_HF_HOME}" \
  "${BDI_HF_HUB_CACHE}" \
  "${BDI_XDG_CACHE_HOME}" \
  "${BDI_VENDOR_ROOT}" \
  "${BDI_SLURM_LOG_ROOT}" \
  "${BDI_SERVICE_LOG_ROOT}" \
  "${BDI_RUN_ROOT}" \
  "${BDI_STATUS_ROOT}"

select_vllm_env_prefix() {
  local env_kind="${1:-stable}"
  case "${env_kind}" in
    stable)
      printf '%s\n' "${BDI_VLLM_STABLE_ENV}"
      ;;
    nightly)
      printf '%s\n' "${BDI_VLLM_NIGHTLY_ENV}"
      ;;
    *)
      printf 'Unsupported ENV_KIND=%s\n' "${env_kind}" >&2
      return 1
      ;;
  esac
}

activate_conda_prefix() {
  local env_prefix="$1"
  source activate "${env_prefix}"
}

write_ready_env_file() {
  local env_kind="$1"
  local env_prefix
  env_prefix="$(select_vllm_env_prefix "${env_kind}")"

  cat > "${BDI_READY_ENV_FILE}" <<EOF
export BDI_SELECTED_VLLM_ENV_KIND=${env_kind}
export BDI_SELECTED_VLLM_ENV_PREFIX=${env_prefix}
export BDI_SELECTED_MODEL_REPO=${BDI_MODEL_REPO}
EOF
}

print_storage_snapshot() {
  local label="${1:-storage snapshot}"
  echo "=== ${label} ==="
  df -h "${HOME}" || true
  for path in \
    "${BDI_PIP_CACHE}" \
    "${BDI_HF_HOME}" \
    "${BDI_ENV_ROOT}" \
    "${BDI_PYTHONUSERBASE}"; do
    if [[ -e "${path}" ]]; then
      timeout 15s du -sh "${path}" 2>/dev/null || echo "snapshot_timeout ${path}"
    fi
  done
}

log_triton_diagnostics() {
  python - <<'PY'
import importlib

def show(label, value):
    print(f"{label}: {value}")

for module_name in ("vllm", "torch", "triton"):
    try:
        module = importlib.import_module(module_name)
        show(f"{module_name}.__version__", getattr(module, "__version__", "unknown"))
    except Exception as exc:
        show(f"{module_name}_import_error", repr(exc))

try:
    triton_kernels = importlib.import_module("triton_kernels")
    show("triton_kernels.__file__", getattr(triton_kernels, "__file__", "unknown"))
except Exception as exc:
    show("triton_kernels_import_error", repr(exc))

try:
    import triton.language as tl
    show("triton.language.constexpr_function", hasattr(tl, "constexpr_function"))
except Exception as exc:
    show("triton.language_import_error", repr(exc))
PY
}

wait_for_openai_compat() {
  local models_url="${1:-http://127.0.0.1:8000/v1/models}"
  local timeout_seconds="${2:-600}"
  local log_file="${3:-/dev/null}"
  local service_pid="${4:-}"
  local waited=0

  until curl -fsS "${models_url}" >/dev/null 2>&1; do
    if [[ -n "${service_pid}" ]] && ! kill -0 "${service_pid}" >/dev/null 2>&1; then
      echo "vLLM process ${service_pid} exited before ${models_url} became ready" >&2
      if [[ -f "${log_file}" ]]; then
        echo "=== Tail of ${log_file} ===" >&2
        tail -n 120 "${log_file}" >&2 || true
      fi
      return 1
    fi
    sleep 5
    waited=$((waited + 5))
    if (( waited >= timeout_seconds )); then
      echo "Timed out waiting for ${models_url} after ${timeout_seconds}s" >&2
      if [[ -f "${log_file}" ]]; then
        echo "=== Tail of ${log_file} ===" >&2
        tail -n 120 "${log_file}" >&2 || true
      fi
      return 1
    fi
  done
}

is_known_triton_failure() {
  local log_file="$1"
  grep -Eq "constexpr_function|triton_kernels|Failed to import Triton kernels" "${log_file}"
}

cleanup_pid_if_running() {
  local pid="${1:-}"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" >/dev/null 2>&1; then
    kill "${pid}" >/dev/null 2>&1 || true
    wait "${pid}" >/dev/null 2>&1 || true
  fi
}
