#!/bin/bash
# run_vllm_glm.sh — user's proven script for GLM-4.7-Flash serving

export PROJECT=/ocean/projects/cis250019p/zjiang9

export SINGULARITYENV_HF_HOME=$PROJECT/hf_cache
export SINGULARITYENV_HF_HUB_CACHE=$PROJECT/hf_cache/hub
export SINGULARITYENV_HUGGINGFACE_HUB_CACHE=$PROJECT/hf_cache/hub

export SINGULARITYENV_VLLM_CACHE_ROOT=$PROJECT/vllm_runtime_cache/vllm
export SINGULARITYENV_TRITON_CACHE_DIR=$PROJECT/vllm_runtime_cache/triton
export SINGULARITYENV_TORCHINDUCTOR_CACHE_DIR=$PROJECT/vllm_runtime_cache/torch_inductor
export SINGULARITYENV_XDG_CACHE_HOME=$PROJECT/vllm_runtime_cache/xdg
export SINGULARITYENV_TMPDIR=$PROJECT/vllm_runtime_cache/tmp

mkdir -p $PROJECT/vllm_runtime_cache/{vllm,triton,torch_inductor,xdg,tmp}
mkdir -p $PROJECT/hf_cache/hub

singularity exec --nv \
  --bind $PROJECT:/project \
  --bind $PROJECT/hf_cache:$PROJECT/hf_cache \
  --bind $PROJECT/vllm_runtime_cache:$PROJECT/vllm_runtime_cache \
  $PROJECT/vllm-openai_latest.sif \
  vllm serve zai-org/GLM-4.7-Flash \
  --tensor-parallel-size 1 \
  --speculative-config.method mtp \
  --speculative-config.num_speculative_tokens 1 \
  --tool-call-parser glm47 \
  --reasoning-parser glm45 \
  --enable-auto-tool-choice \
  --served-model-name glm-4.7-flash \
  --max-model-len 65536 \
  --port 47259
