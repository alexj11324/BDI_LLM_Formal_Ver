# Entity Memory Store — BDI-LLM (PNSV) Project
> Generated: 2026-03-05 | Layer: conversation-memory (存储层)

## Core Entities

### 🏗️ Systems & Frameworks

| Entity | Type | Properties |
|--------|------|------------|
| **PNSV** | Framework | Pluggable Neuro-Symbolic Verification; domain-agnostic BDI reasoning engine |
| **BDI Engine** | Core Module | DSPy-based; generates Intention DAGs from LLM output |
| **Structural Verifier** | Verification Layer | Uses NetworkX DAG; checks plan topology |
| **Symbolic Verifier** | Verification Layer | Uses PDDL + VAL binary; validates plan against formal domain model |
| **Dynamic Replanner** | Subsystem | Runtime re-planning when execution diverges from expected world state |
| **BeliefBase** | Component | Parses PDDL `:init`; tracks propositions; applies STRIPS effects |
| **PlanExecutor** | Component | Simulates action execution; triggers replanner on divergence |
| **Checkpoint/Resume** | Feature | Atomic JSON writes (`tmp → rename`); `--resume` flag on evaluator |

### 🤖 Models & Services

| Entity | Type | Properties |
|--------|------|------------|
| **qwq-plus** | LLM Model | Alibaba Cloud; deep-reasoning; used for batch inference |
| **qwen3.5-plus** | LLM Model | Alibaba Cloud; current primary model in `.env` |
| **DashScope** | API Service | OpenAI-compatible endpoint; requires `DASHSCOPE_API_KEY` |
| **litellm** | Library | LLM routing layer; wraps DashScope calls |

### 📁 Key Files

| Entity | Path | Role |
|--------|------|------|
| **belief_base.py** | `src/bdi_llm/dynamic_replanner/belief_base.py` | PDDL state parsing + STRIPS effects |
| **replanner.py** | `src/bdi_llm/dynamic_replanner/replanner.py` | Replanning orchestrator |
| **executor.py** | `src/bdi_llm/dynamic_replanner/executor.py` | Plan step execution + divergence detection |
| **planner.py** | `src/bdi_llm/planner.py` | Main LLM plan generation; timeout = 600s |
| **run_dynamic_replanning.py** | `scripts/replanning/run_dynamic_replanning.py` | E2E evaluator with checkpoint resume |
| **.env** | `.env` | Model config, API endpoint, timeout settings |

### 🌍 Domains

| Entity | Type | Status |
|--------|------|--------|
| **Blocksworld** | PlanBench Domain | Primary test domain; 1 instance tested (Init failed due to API key) |
| **Logistics** | PlanBench Domain | Registered; not yet tested in replanning pipeline |
| **Depots** | PlanBench Domain | Registered; not yet tested in replanning pipeline |

## Entity Relationships

```
PNSV ──uses──► BDI Engine ──calls──► litellm ──routes──► DashScope (qwen3.5-plus)
  │                                                          │
  ├──contains──► Structural Verifier (NetworkX)               requires── DASHSCOPE_API_KEY
  ├──contains──► Symbolic Verifier (PDDL + VAL)
  └──contains──► Dynamic Replanner
                    ├──uses──► BeliefBase (PDDL state)
                    ├──uses──► PlanExecutor (simulation)
                    └──writes──► Checkpoint JSON (atomic)

Evaluator (run_dynamic_replanning.py)
  ├──iterates──► Blocksworld instances
  ├──iterates──► Logistics instances
  └──iterates──► Depots instances
```

## Persistent Facts (Cross-Session)

- `Config.TIMEOUT` = 600 seconds (unified across all LLM calls)
- `python-dotenv` does NOT support `${VAR}` shell expansion
- Auto-repair features live on `feature/repair` branch, never on `main`
- Evaluation script is `scripts/evaluation/run_verification_only.py` (verification) or `scripts/replanning/run_dynamic_replanning.py` (replanning)
- VAL binary path: system-installed, invoked via `subprocess.run`
