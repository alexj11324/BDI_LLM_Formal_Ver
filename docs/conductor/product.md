# Product Definition

## Project Name
BDI-LLM Formal Verification (PNSV)

## Description
A neuro-symbolic planning framework that wraps LLM-generated plans in a BDI cognitive architecture with formal verification and auto-repair, proving that structured reasoning + verification can elevate LLM plan correctness from naive baselines to provably correct outputs.

## Problem Statement
LLMs generate action plans that frequently contain hallucinated or physically impossible steps. Without formal verification, these plans cannot be trusted for safety-critical or correctness-dependent applications. Existing approaches either sacrifice LLM flexibility (pure symbolic planners) or lack verification guarantees (pure LLM planners).

## Target Users
- **ML/AI Researchers**: Studying plan generation, formal verification, and neuro-symbolic AI
- **AI Agent Developers**: Building agents (Claude Code, Cursor) that need verified planning capabilities
- **Framework Contributors**: Extending PNSV with new domains and verification layers

## Key Goals
1. Demonstrate that BDI + 3-layer verification + auto-repair elevates LLM plan correctness to 100% on PDDL benchmarks
2. Achieve state-of-the-art results on TravelPlanner multi-constraint benchmark
3. Expose the verification loop as a reusable MCP server for agent integration
