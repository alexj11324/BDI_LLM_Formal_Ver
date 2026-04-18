#!/bin/bash
# run_vllm.sh — GLM-4.7-Flash with HF cache on node-local /local NVMe
# (mirrors qwen36/run_vllm.sh exactly: HF Hub → /local NVMe direct, no Lustre hop).
#
# First run on a node: HF downloads ~59GB from CDN to /local NVMe (~10-20 min).
# Subsequent runs on same node: cached, model load is seconds.
#
# RULE: never rsync from /ocean → /local — Lustre IO contention is unpredictable
# and can saturate shared OSTs. Direct HF download uses parallel CDN chunks,
# completely bypassing Lustre. See feedback_hf_cache_local_nvme_direct.md.

set -eu
export PROJECT=/ocean/projects/cis250019p/zjiang9
export LOCAL_CACHE=/local/${USER:-zjiang9}/hf_cache

# HF caches pinned to node-local NVMe (fast, no Lustre hop)
export SINGULARITYENV_HF_HOME=$LOCAL_CACHE
export SINGULARITYENV_HF_HUB_CACHE=$LOCAL_CACHE/hub
export SINGULARITYENV_HUGGINGFACE_HUB_CACHE=$LOCAL_CACHE/hub

# torch.compile / vllm / triton caches — keep on /ocean so they persist
# across nodes (compile cache is expensive to rebuild).
export SINGULARITYENV_VLLM_CACHE_ROOT=$PROJECT/vllm_runtime_cache/vllm
export SINGULARITYENV_TRITON_CACHE_DIR=$PROJECT/vllm_runtime_cache/triton
export SINGULARITYENV_TORCHINDUCTOR_CACHE_DIR=$PROJECT/vllm_runtime_cache/torch_inductor
export SINGULARITYENV_XDG_CACHE_HOME=$PROJECT/vllm_runtime_cache/xdg
export SINGULARITYENV_TMPDIR=$LOCAL_CACHE/tmp

mkdir -p $LOCAL_CACHE/hub $LOCAL_CACHE/tmp
mkdir -p $PROJECT/vllm_runtime_cache/{vllm,triton,torch_inductor,xdg}

echo "===== GLM-4.7-Flash launcher (local-NVMe variant, no rsync) ====="
echo "Node:           $(hostname)"
echo "HF cache:       $LOCAL_CACHE"
echo "Free /local:    $(df -h /local 2>/dev/null | tail -1 | awk '{print $4}')"
echo "=== existing cache in /local ==="
ls -lah $LOCAL_CACHE/hub/ 2>/dev/null | head -5 || echo "(empty, will download from HF Hub on first run)"
echo "================================"

singularity exec --nv \
  --bind $PROJECT:/project \
  --bind $LOCAL_CACHE:$LOCAL_CACHE \
  --bind $PROJECT/vllm_runtime_cache:$PROJECT/vllm_runtime_cache \
  $PROJECT/vllm-openai_latest.sif \
  vllm serve zai-org/GLM-4.7-Flash \
  --port ${PORT:-47259} \
  --tensor-parallel-size ${TP_SIZE:-1} \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.90 \
  --speculative-config.method mtp \
  --speculative-config.num_speculative_tokens 1 \
  --tool-call-parser glm47 \
  --reasoning-parser glm45 \
  --enable-auto-tool-choice \
  --served-model-name glm-4.7-flash
