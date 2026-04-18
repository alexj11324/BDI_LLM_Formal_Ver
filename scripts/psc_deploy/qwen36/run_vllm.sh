#!/bin/bash
# run_vllm_qwen.sh
# Official Qwen3.6-35B-A3B serving script with MTP + text-only + all parsers.

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
  vllm serve Qwen/Qwen3.6-35B-A3B \
  --port ${PORT:-47260} \
  --tensor-parallel-size 1 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90 \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder \
  --enable-auto-tool-choice \
  --speculative-config '{"method":"qwen3_next_mtp","num_speculative_tokens":2}' \
  --language-model-only \
  --served-model-name qwen3.6-35b-a3b
