#!/bin/bash
# run_vllm.sh — GLM-4.7-Flash with HF cache on node-local /local NVMe
# (mirrors qwen36/run_vllm.sh layout: bypass Lustre /ocean for weight I/O).
#
# Pre-warm: if /ocean canonical copy exists, rsync 59GB → /local in ~1 min
# (Lustre→NVMe ~1GB/s) instead of paying the ~10-20 min HF Hub redownload.
# First run on a brand-new node with no /ocean copy: HF downloads from CDN.

set -eu
export PROJECT=/ocean/projects/cis250019p/zjiang9
export LOCAL_CACHE=/local/${USER:-zjiang9}/hf_cache
export OCEAN_HF=$PROJECT/hf_cache
export MODEL_REPO=models--zai-org--GLM-4.7-Flash

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

echo "===== GLM-4.7-Flash launcher (local-NVMe variant) ====="
echo "Node:           $(hostname)"
echo "HF cache:       $LOCAL_CACHE"
echo "Free /local:    $(df -h /local 2>/dev/null | tail -1 | awk '{print $4}')"

# Pre-warm: rsync /ocean canonical → /local NVMe if missing
if [ -d "$OCEAN_HF/hub/$MODEL_REPO" ] && [ ! -d "$LOCAL_CACHE/hub/$MODEL_REPO/snapshots" ]; then
  echo "[pre-warm] rsync $OCEAN_HF/hub/$MODEL_REPO -> $LOCAL_CACHE/hub/ ..."
  t0=$(date +%s)
  rsync -aHL --info=progress2 "$OCEAN_HF/hub/$MODEL_REPO" "$LOCAL_CACHE/hub/" || \
    echo "[pre-warm] rsync failed — will fall back to HF Hub download"
  echo "[pre-warm] done in $(($(date +%s) - t0))s"
fi

echo "=== existing cache in /local ==="
ls -lah $LOCAL_CACHE/hub/ 2>/dev/null | head -5 || echo "(empty, will download on first run)"
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
