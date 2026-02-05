#!/bin/bash
# Ralph Environment Setup Script
# Source this file before running Ralph: source .ralph_env.sh

# Export API credentials for BDI-LLM Framework
export OPENAI_API_KEY=sk-CAMQPAfhTgcWPrFfxm_1Zg
export OPENAI_API_BASE=https://ai-gateway.andrew.cmu.edu/v1

echo "✓ API credentials loaded for Ralph"
echo "  OPENAI_API_KEY: ${OPENAI_API_KEY:0:15}... (masked)"
echo "  OPENAI_API_BASE: $OPENAI_API_BASE"
