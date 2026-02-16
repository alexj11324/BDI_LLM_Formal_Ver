# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BDI-LLM is a neuro-symbolic planning framework that combines LLM generation (via DSPy) with formal verification to produce provably correct plans. It evaluates on the PlanBench benchmark across three classical planning domains: Blocksworld, Logistics, and Depots.

Core pipeline: Natural language input → LLM plan generation (DSPy ChainOfThought) → 3-layer verification (structural + VAL symbolic + domain physics) → error-driven repair loop → verified PDDL plan.

## Commands

```bash
# Install
pip install -r requirements.txt

# Run all tests (no API key needed for unit tests)
pytest

# Run a single test file
pytest tests/test_verifier.py -v

# Evaluation modes
python scripts/run_evaluation.py --mode unit          # offline unit tests
python scripts/run_evaluation.py --mode demo-offline  # offline demo
python scripts/run_evaluation.py --mode demo          # needs API key
python scripts/run_evaluation.py --mode benchmark     # needs API key

# PlanBench full evaluation
python scripts/run_planbench_full.py --domain blocksworld --max_instances 100
python scripts/run_planbench_full.py --all_domains --max_instances 50
python scripts/run_planbench_full.py --domain blocksworld --resume runs/checkpoint.json

# Verify frozen paper data integrity
python scripts/verify_paper_eval_snapshot.py
```

## Architecture

### Core Modules (`src/bdi_llm/`)

- **`schemas.py`** — Pydantic models: `ActionNode`, `DependencyEdge`, `BDIPlan` (with `to_networkx()`)
- **`planner.py`** — DSPy-based planner with domain-specific Signatures (`GeneratePlan`, `GeneratePlanLogistics`, `GeneratePlanDepots`) and `RepairPlan`. Each Signature embeds state-tracking tables, chain-of-symbol representations, and domain constraints. Logistics includes few-shot demonstrations from VAL-validated gold plans.
- **`verifier.py`** — Layer 1: structural validation (DAG check, weak connectivity, cycle detection, topological sort)
- **`symbolic_verifier.py`** — Layer 2: PDDL symbolic verification via VAL binary; Layer 3: domain-specific physics (e.g., `BlocksworldPhysicsValidator` simulates clear/hand state). `IntegratedVerifier` orchestrates all three layers.
- **`plan_repair.py`** — Auto-repair: connects disconnected subgraphs (virtual START/END nodes), canonicalizes node IDs. `repair_and_verify()` is the main entry point.
- **`config.py`** — Central config from env vars/.env. Supports OpenAI (default gpt-4o), Gemini, Vertex AI, Anthropic via litellm.

### Data Flow

```
BDIPlanner.forward() → DSPy ChainOfThought → action constraint validation →
NetworkX graph → PlanVerifier → [auto-repair if disconnected] →
PDDLSymbolicVerifier (VAL) → PhysicsValidator →
[repair_from_val_errors loop, up to 3 attempts] → verified plan
```

### Key External Dependencies

- **VAL binary**: `planbench_data/planner_tools/VAL/validate` — auto-detected by `symbolic_verifier.py`
- **PlanBench data**: `planbench_data/plan-bench/` — PDDL problem/domain files
- **DSPy 3.x**: `dspy.Assert`/`dspy.Suggest` are removed; use native `raise ValueError` instead

## Important Conventions

- **`artifacts/paper_eval_20260213/`** is an immutable frozen evidence snapshot for the paper. Never modify these files. Paper figures/tables must derive only from this directory.
- **`runs/`** is mutable, non-authoritative output. Do not use for paper claims.
- Environment variables: `LLM_MODEL` (default `openai/gpt-4o`), `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`. See `.env.example`.
- Tests in `tests/test_integration*.py` require API keys; all other tests run offline.
- The paper LaTeX source is in `BDI_Paper/` (AAAI 2026 format).
