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
pytest tests/unit/test_verifier.py -v

# Evaluation modes
python scripts/evaluation/run_evaluation.py --mode unit          # offline unit tests
python scripts/evaluation/run_evaluation.py --mode demo-offline  # offline demo
python scripts/evaluation/run_evaluation.py --mode demo          # needs API key
python scripts/evaluation/run_evaluation.py --mode benchmark     # needs API key

# PlanBench full evaluation
python scripts/evaluation/run_planbench_full.py --domain blocksworld --max_instances 100
python scripts/evaluation/run_planbench_full.py --all_domains --max_instances 50
python scripts/evaluation/run_planbench_full.py --domain blocksworld --resume runs/checkpoint.json

# Ablation modes (NAIVE / BDI_ONLY / FULL_VERIFIED) — sets AGENT_EXECUTION_MODE internally
python scripts/evaluation/run_planbench_full.py --all_domains --execution_mode NAIVE --output_dir runs/ablation_NAIVE --parallel --workers 30
python scripts/evaluation/run_planbench_full.py --all_domains --execution_mode BDI_ONLY --output_dir runs/ablation_BDI_ONLY --parallel --workers 30

# MCP server (exposes generate_verified_plan tool to Claude Code / Cursor / etc.)
python src/interfaces/mcp_server.py

# SWE-bench harness
python scripts/swe_bench/swe_bench_harness.py

# Verify frozen paper data integrity
python scripts/evaluation/verify_paper_eval_snapshot.py
```

## Architecture

### Core Modules (`src/bdi_llm/`)

- **`schemas.py`** — Pydantic models: `ActionNode`, `DependencyEdge`, `BDIPlan` (with `to_networkx()`)
- **`planner.py`** — DSPy-based planner with domain-specific Signatures (`GeneratePlan`, `GeneratePlanLogistics`, `GeneratePlanDepots`) and `RepairPlan`. Each Signature embeds state-tracking tables, chain-of-symbol representations, and domain constraints. Logistics includes few-shot demonstrations from VAL-validated gold plans.
- **`verifier.py`** — Layer 1: structural validation (DAG check, weak connectivity, cycle detection, topological sort)
- **`symbolic_verifier.py`** — Layer 2: PDDL symbolic verification via VAL binary; Layer 3: domain-specific physics (e.g., `BlocksworldPhysicsValidator` simulates clear/hand state). `IntegratedVerifier` orchestrates all three layers.
- **`plan_repair.py`** — Auto-repair: connects disconnected subgraphs (virtual START/END nodes), canonicalizes node IDs. `repair_and_verify()` is the main entry point.
- **`config.py`** — Central config from env vars/.env. Supports OpenAI (default gpt-4o), Gemini, Vertex AI, Anthropic via litellm.
- **`coding_planner.py`** — Extends `BDIPlanner` for the SWE-bench coding domain. Defines `GeneratePlanCoding` DSPy Signature with coding-specific action types (`read-file`, `edit-file`, `run-test`, `create-file`) and `CodingBDIPlanner`.
- **`visualizer.py`** — Graph visualization utilities for BDI plan DAGs.

### MCP Server

`src/interfaces/mcp_server.py` exposes a `generate_verified_plan` FastMCP tool. External agents (Claude Code, Cursor, etc.) call it with a `PlanRequest` (goal, domain, context, PDDL paths) and receive a verified plan or error report. Entry point for production use.

### SWE-bench Path

`scripts/swe_bench/swe_bench_harness.py` uses `CodingBDIPlanner` + `PlanVerifier` to run BDI-LLM on SWE-bench instances. Clones repos locally, applies edits, runs tests. `scripts/swe_bench/run_swe_bench_batch.py` batches multiple instances.

### Ablation Modes

`AGENT_EXECUTION_MODE` env var (set automatically by `--execution_mode` flag) controls verification depth:
- `NAIVE` — LLM generation only, no verification
- `BDI_ONLY` — structural verification (Layer 1) only
- `FULL_VERIFIED` — all 3 layers + repair loop (default)

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

## Benchmark Run History & Results

### Completed Full-Dataset Runs

| Model | Date | Blocksworld | Logistics | Depots | Overall | Artifacts |
|-------|------|-------------|-----------|--------|---------|-----------|
| Gemini | 2026-02-13 | ~200/200 | 568/570 (99.6%) | 497/500 (99.4%) | — | `artifacts/paper_eval_20260213/` (frozen) |
| openai/gpt-5 (infiniteai) | 2026-02-23 | 1103/1103 (100%) | 561/572 (98.1%) | 493/501 (98.4%) | 2157/2176 (99.1%) | `mlruns/1,2,3/` |

- **Gemini run** = paper canonical numbers. Stored in frozen `artifacts/paper_eval_20260213/`. Blocksworld only ran ~200 instances.
- **GPT-5 run** = full-dataset run via `infiniteai.cc` (`openai/gpt-5`，`.env` 配置). Orchestrated by Codex CLI, but benchmark LLM calls went to infiniteai. Results in `mlruns/`. Auto-repair worked for depots (8/8), failed for logistics (11 failures unrepaired).
- **`runs/scientist_team_dryrun_impl*/`** = empty dry-run shells generated by Codex CLI orchestration, no real benchmark data. Ignore.
- **Dataset full sizes**: blocksworld ≈ 1103 instances, logistics = 572, depots = 501 (PDDL files in `planbench_data/plan-bench/instances/`).
- **Checkpoint/resume**: `run_planbench_full.py` auto-resumes if checkpoint exists in output dir. All GPT-5 runs are complete; no resume needed.

### API / Model Configuration

Two separate roles — do not conflate:

- **`.env` (benchmark LLM)**: `OPENAI_API_BASE=https://api.infiniteai.cc/v1`, `LLM_MODEL=openai/gpt-5` — used by `config.py` / `run_planbench_full.py` for actual plan generation
- **LiteLLM proxy (nebula)**: `https://api.nebula-spaces.com/v1`, model `gpt-5.3-codex`, key `sk-litellm-local` — used by Codex CLI as orchestrator, not for benchmark LLM calls

To check if nebula proxy is up: `curl -s https://api.nebula-spaces.com/v1/models -H "Authorization: Bearer sk-litellm-local"`
Available models: `sonnet-4-6`, `opus-4-6`, `huan-grok-4-2`, `gpt-5.3-codex`, `gpt-5.3-codex-response`

No built-in API health-check script exists in `scripts/` — add one if needed.

## 当前进行中的跑（2026-02-27，待明天继续）

### 状态：infiniteai quota 用完，明天重启

**进度快照（2026-02-27 晚）：**

| Run | blocksworld | logistics | depots |
|-----|-------------|-----------|--------|
| FULL_VERIFIED (`runs/benchmark_gpt5_full`) | ✅ 1103/1103 (90.8% sr) | ~300/572 (未完成) | 未开始 |
| NAIVE (`runs/ablation_NAIVE`) | ✅ 1103/1103 (91.6% sr) | ~571/572 (未完成) | 未开始 |
| BDI_ONLY (`runs/ablation_BDI_ONLY`) | ✅ 1103/1103 (91.7% sr) | ✅ 572/572 (82.9% sr) | 进行中 |

**失败原因**：logistics 大量失败是 504 Gateway Timeout（quota 耗尽），不是计划质量问题。真实 sr 约 99%。

**明天重启步骤：**

1. 运行 `strip_timeouts.py` 清掉 checkpoint 里的 timeout 失败记录：
```python
# scripts/strip_timeouts.py
import json, os
PROJ = '/Users/alexjiang/Desktop/BDI_LLM_Formal_Ver'
runs = ['benchmark_gpt5_full', 'ablation_NAIVE', 'ablation_BDI_ONLY']
domains = ['blocksworld', 'logistics', 'depots']
for run in runs:
    for domain in domains:
        ckpt = f'{PROJ}/runs/{run}/checkpoint_{domain}.json'
        if not os.path.exists(ckpt): continue
        with open(ckpt) as f: d = json.load(f)
        before = len(d['results'])
        d['results'] = [r for r in d['results']
            if r.get('success') or 'Timeout' not in str(r.get('bdi_metrics', {}))]
        after = len(d['results'])
        if before != after:
            with open(ckpt, 'w') as f: json.dump(d, f, indent=2)
            print(f'{run}/{domain}: removed {before-after} timeout failures')
```

2. 用 `--workers 30` 重启（不要用 200，会再次打爆 quota）：
```bash
PYTHON=/Users/alexjiang/opt/anaconda3/envs/ai_scientist/bin/python
PROJ=/Users/alexjiang/Desktop/BDI_LLM_Formal_Ver
cd $PROJ

tmux new-session -d -s bdi_bench -n full_verified
tmux send-keys -t bdi_bench:full_verified "$PYTHON scripts/evaluation/run_planbench_full.py --all_domains --execution_mode FULL_VERIFIED --output_dir runs/benchmark_gpt5_full --parallel --workers 30" Enter

tmux new-window -t bdi_bench -n ablation_naive
tmux send-keys -t bdi_bench:ablation_naive "$PYTHON scripts/evaluation/run_planbench_full.py --all_domains --execution_mode NAIVE --output_dir runs/ablation_NAIVE --parallel --workers 30" Enter

tmux new-window -t bdi_bench -n ablation_bdi_only
tmux send-keys -t bdi_bench:ablation_bdi_only "$PYTHON scripts/evaluation/run_planbench_full.py --all_domains --execution_mode BDI_ONLY --output_dir runs/ablation_BDI_ONLY --parallel --workers 30" Enter
```

checkpoint 会自动 resume，只补跑失败的实例。

---

## Benchmark Execution Environment

**始终在本地 Mac 上跑 benchmark，不要在 OCI 上跑。** 原因：
- VAL 二进制（`planbench_data/planner_tools/VAL/validate`）是 macOS arm64 Mach-O，在 Linux aarch64 上无法执行
- 历史上所有成功的跑（包括 GPT-5 全量跑）都是在本地跑的，OCI 只用来跑其他服务
- 本地 benchmark 用 `ai_scientist` conda env：`/Users/alexjiang/opt/anaconda3/envs/ai_scientist/bin/python`

本地启动全量 + 消融跑（tmux）：
```bash
PYTHON=/Users/alexjiang/opt/anaconda3/envs/ai_scientist/bin/python
PROJ=/Users/alexjiang/Desktop/BDI_LLM_Formal_Ver
cd $PROJ

# 全量
tmux new-session -d -s bdi_bench -n full_verified
tmux send-keys -t bdi_bench:full_verified "$PYTHON scripts/evaluation/run_planbench_full.py --all_domains --execution_mode FULL_VERIFIED --output_dir runs/benchmark_gpt5_full --workers 50 2>&1 | tee runs/benchmark_gpt5_full.log" Enter

# 消融
tmux new-window -t bdi_bench -n ablation_naive
tmux send-keys -t bdi_bench:ablation_naive "$PYTHON scripts/evaluation/run_planbench_full.py --all_domains --execution_mode NAIVE --output_dir runs/ablation_NAIVE --workers 50 2>&1 | tee runs/ablation_NAIVE.log" Enter

tmux new-window -t bdi_bench -n ablation_bdi_only
tmux send-keys -t bdi_bench:ablation_bdi_only "$PYTHON scripts/evaluation/run_planbench_full.py --all_domains --execution_mode BDI_ONLY --output_dir runs/ablation_BDI_ONLY --workers 50 2>&1 | tee runs/ablation_BDI_ONLY.log" Enter
```

## ResponsesAPILM（infiniteai + gpt-5）

`planner.py` 中的 `ResponsesAPILM` 适配类，用于 infiniteai 的 `/v1/responses` 接口。关键教训：
- **必须继承 `dspy.BaseLM`**，不能只实现 `__call__`，否则 DSPy 会拒绝接受
- **infiniteai 只支持 SSE 流式返回**，非流式接口从 OCI IP 访问会被 block；用 `requests` 直接 POST + `stream=True` 解析 SSE
- **`system` role 在 input[] 里会 400**，必须把 system 消息内容放进 `instructions` 顶层字段，而不是 `input` 数组

## Important Conventions

- **`artifacts/paper_eval_20260213/`** is an immutable frozen evidence snapshot for the paper. Never modify these files. Paper figures/tables must derive only from this directory.
- **`runs/`** is mutable, non-authoritative output. Do not use for paper claims.
- **Benchmark rerun lock**: `runs/completed_benchmarks.lock.json` is the default do-not-rerun list for completed benchmark groups. Reuse existing artifacts unless the user explicitly requests a rerun in the current task.
- **`runs/disabled_obfuscated/` and obfuscated domains are disabled by policy**. Do not launch or resume benchmarks for `obfuscated_*` domains unless the user explicitly overrides this rule in the current task.
- Environment variables: `LLM_MODEL` (default `openai/gpt-4o`), `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`. See `.env.example`.
- Tests in `tests/test_integration*.py` require API keys; all other tests run offline.
- The paper LaTeX source is in `BDI_Paper/` (AAAI 2026 format).
