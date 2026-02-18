---
activation: always_on
description: Core project context for BDI LLM Formal Verification. Always loaded so Agent understands the project across sessions.
---

# BDI Formal Verification Project Context

## Project Identity
- **Repo**: `BDI_LLM_Formal_Ver`
- **Goal**: Provide a BDI-based formal plan verification and self-repair service for LLM agents
- **What it does**: Agent generates a plan → this system verifies it (PDDL/VAL) → if invalid, diagnoses why → auto-repairs → re-verifies until pass or give up
- **What it is NOT**: This is NOT a full agent. It's an MCP tool that existing agents (Antigravity, Claude Code, Cursor, etc.) call to verify and fix their plans.
- **Targets**: >99% PlanBench verification accuracy, >90% SWE-bench plan repair rate

## Architecture
- **Planner**: DSPy-based `BDIPlanner` (`src/bdi_llm/planner.py`)
- **Verifier**: PDDL + VAL (`src/bdi_llm/symbolic_verifier.py`)
- **MCP Server**: `src/mcp_server_bdi.py` exposes `generate_verified_plan` tool
- **Domains**: blocksworld, logistics, depots (existing), coding (planned)

## Key Files
- Plans: `src/bdi_llm/planner.py` (DSPy signatures, plan generation)
- Schemas: `src/bdi_llm/schemas.py` (BDIPlan, ActionNode, DependencyEdge)
- Verification: `src/bdi_llm/symbolic_verifier.py` (VAL integration)
- VAL binary: `planbench_data/planner_tools/VAL/validate`
- Tests: `tests/test_mcp_bdi_integration.py`

## Conventions
- Python 3.13, use type hints
- Tests with pytest
- PDDL domains in `planbench_data/`
- Always verify plans before execution

## Current Iteration State
Check Memory MCP (`memory_search` with query "iteration-state") for latest evaluation results,
failure patterns, and next improvement targets from previous sessions.
