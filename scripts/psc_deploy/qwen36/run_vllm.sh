#!/bin/bash
# run_vllm_qwen.sh — Qwen3.6-35B-A3B with HF cache on node-local /local NVMe
# (bypasses Lustre /ocean for weight I/O).
#
# First run on a new node: HF downloads ~60-70GB from HuggingFace CDN into
# /local/$USER/hf_cache. Subsequent runs on the same node: read from local
# NVMe (GB/s), model load is seconds.

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

echo "===== Qwen3.6 launcher (local-NVMe variant) ====="
echo "Node:           $(hostname)"
echo "HF cache:       $LOCAL_CACHE"
echo "Free /local:    $(df -h /local 2>/dev/null | tail -1 | awk '{print $4}')"
echo "=== existing cache in /local ==="
ls -lah $LOCAL_CACHE/hub/ 2>/dev/null | head -5 || echo "(empty, will download on first run)"
echo "================================"

singularity exec --nv \
  --bind $PROJECT:/project \
  --bind $LOCAL_CACHE:$LOCAL_CACHE \
  --bind $PROJECT/vllm_runtime_cache:$PROJECT/vllm_runtime_cache \
  $PROJECT/vllm-openai_latest.sif \
  vllm serve Qwen/Qwen3.6-35B-A3B \
  --port ${PORT:-47260} \
  --tensor-parallel-size ${TP_SIZE:-4} \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.90 \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder \
  --enable-auto-tool-choice \
  --speculative-config '{"method":"qwen3_next_mtp","num_speculative_tokens":2}' \
  --language-model-only \
  --served-model-name qwen3.6-35b-a3b
