# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Runtime scope

The active runtime is the `src/bdi_llm/` package, the entrypoints in `src/interfaces/`, and the current runners in `scripts/evaluation/` and `scripts/replanning/`.

Do **not** treat these as the mainline runtime unless a task explicitly says so:
- `scripts/evaluation/_legacy/` — historical runners kept for reference
- `scripts/swe_bench/` — SWE-bench subsystem has been removed/deferred; no active runner here

## Setup and common commands

### Install

Use the package metadata in `pyproject.toml` for development installs:

```bash
pip install -e ".[dev]"
cp .env.example .env
```

`requirements.txt` is only a minimal subset and is not the best source for a full local dev environment.

### Lint

```bash
ruff check .
```

### Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit -q

# Single test file
pytest tests/unit/test_travelplanner_review.py -q

# Single test
pytest tests/unit/test_travelplanner_review.py::test_apply_patch_preserves_untouched_days -q

# Offline VAL / symbolic integration
pytest tests/integration/test_val_integration.py -q

# API-backed planner integration
pytest tests/integration/test_integration.py -q
```

Notes:
- Most unit tests are offline.
- `tests/integration/test_integration.py` exercises live planner generation and needs API credentials.
- Local symbolic verification needs a working VAL binary at `planbench_data/planner_tools/VAL/validate`.

### Demo and MCP entrypoints

Run these after an editable install so `bdi_llm` imports resolve correctly:

```bash
python src/interfaces/cli.py
python src/interfaces/mcp_server.py
```

### Generic PDDL / PlanBench-style evaluation

```bash
# Single generic PDDL problem
python scripts/evaluation/run_generic_pddl_eval.py --domain_pddl tests/fixtures/gripper/domain.pddl --problem_pddl tests/fixtures/gripper/problem1.pddl

# Batch generic PDDL directory with VAL checking
python scripts/evaluation/run_generic_pddl_eval.py --domain_pddl tests/fixtures/gripper/domain.pddl --problem_dir tests/fixtures/gripper --execution_mode VERIFY_WITH_VAL

# Built-in PlanBench paper-aligned evaluation
python scripts/evaluation/run_planbench_paperaligned.py --domain blocksworld --execution_mode bdi-repair --max_instances 10
```

Use `run_generic_pddl_eval.py` as the current generic PDDL runner. Do not default to `_legacy/run_planbench_full.py` unless the task is explicitly about the old pipeline.

### TravelPlanner

```bash
python scripts/evaluation/run_travelplanner_baseline.py --split validation --max_instances 3 --travelplanner_home /path/to/TravelPlanner_official
python scripts/evaluation/run_travelplanner_bdi.py --split validation --max_instances 3 --travelplanner_home /path/to/TravelPlanner_official
python scripts/evaluation/run_travelplanner_repair.py --split validation --max_instances 3 --travelplanner_home /path/to/TravelPlanner_official

# Release matrix / validation orchestration
python scripts/evaluation/run_travelplanner_release_matrix.py --run-validation --workers 20 --travelplanner-home /path/to/TravelPlanner_official

# Generate test-set submissions
python scripts/evaluation/run_travelplanner_test_submit.py --mode bdi-repair --output_dir runs/tp_test_submit --workers 100
```

TravelPlanner requires an external checkout of the official repo. It is **not** stored in this repo.
Supply the path via the `TRAVELPLANNER_HOME` environment variable or the `--travelplanner_home` CLI flag.
The checkout must contain the official database files, and the Hugging Face `osunlp/TravelPlanner` dataset
must be accessible.

## Configuration and runtime assumptions

Configuration lives in `src/bdi_llm/config.py` and is loaded from the environment plus `.env`.

Important variables:
- `OPENAI_API_KEY`
- `OPENAI_API_BASE`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `GOOGLE_APPLICATION_CREDENTIALS`
- `LLM_MODEL`
- `VAL_VALIDATOR_PATH`
- `SAVE_REASONING_TRACE`
- `REASONING_TRACE_MAX_CHARS`

Important detail: `Config._resolve_key()` ignores placeholder strings like `${VAR}`. Put real values in `.env` or export them in the shell.

The current runtime resolves VAL under:
- `planbench_data/planner_tools/VAL/validate`

If local symbolic verification fails on macOS, check executable permissions:

```bash
chmod +x planbench_data/planner_tools/VAL/validate
```

## High-level architecture

### 1. Benchmark inputs are normalized into `PlanningTask`

`src/bdi_llm/planning_task.py` defines the benchmark-agnostic planner contract:
- `PlanningTask` — normalized `beliefs`, `desire`, and optional `domain_context`
- `TaskAdapter` — converts benchmark-native inputs into `PlanningTask`
- `PlanSerializer` — converts planner outputs back into benchmark-native format

For generic PDDL, `PDDLTaskAdapter` turns problem files into natural-language beliefs/goals, and `PDDLPlanSerializer` converts a `BDIPlan` back into grounded PDDL actions.

### 2. `BDIPlan` is the core planning data structure

`src/bdi_llm/schemas.py` defines:
- `ActionNode`
- `DependencyEdge`
- `BDIPlan`

`BDIPlan` is a DAG-shaped intermediate plan representation that can be converted to `networkx` for verification.

### 3. `DomainSpec` separates built-in domains from generic PDDL

`src/bdi_llm/planner/domain_spec.py` is the domain abstraction layer.

It provides:
- built-in specs for `blocksworld`, `logistics`, and `depots`
- `DomainSpec.from_pddl()` for arbitrary PDDL domains
- parsed action schemas, required parameters, and prompt-facing `domain_context`
- optional few-shot demonstrations for some domains

This is the reason the planner can serve both fixed benchmark domains and arbitrary PDDL domains without hardcoding everything in the planner constructor.

### 4. `BDIPlanner` is the main DSPy planning module

`src/bdi_llm/planner/bdi_engine.py` is the main planning entrypoint.

Key behaviors:
- `generate_plan()` does plan generation only
- `forward()` adds structural verification on top of generation
- `_validate_action_constraints()` checks action names and required params against the active `DomainSpec`
- `repair_from_val_errors()` performs verifier-guided repair with cache/budget controls

Supporting modules:
- `src/bdi_llm/api_budget.py` — rate limits / repair budget policy
- `src/bdi_llm/repair_cache.py` — avoids repeating identical repair work
- `src/bdi_llm/plan_repair.py` — graph-shape repair such as cycle breaking or reconnecting disconnected components

### 5. Verification is layered

There are two distinct verification layers and they should not be conflated:

- `src/bdi_llm/verifier.py` — **structural** verification only
  - empty graph = hard failure
  - cycle = hard failure
  - disconnected components = warning, not a blocker

- `src/bdi_llm/symbolic_verifier.py` — **symbolic / domain** verification
  - `PDDLSymbolicVerifier` wraps VAL
  - `IntegratedVerifier` orchestrates symbolic + optional domain-specific checks
  - `BlocksworldPhysicsValidator` adds Python-side simulation checks beyond raw VAL output

When debugging failures, first determine whether the issue is:
- graph structure
- PDDL executability / VAL
- domain-specific semantics

### 6. MCP server is a thin interface over the planner/verifier stack

`src/interfaces/mcp_server.py` exposes three FastMCP tools:
- `generate_plan`
- `verify_plan`
- `execute_verified_plan`

`execute_verified_plan` is the gated-execution path: it only runs the requested shell command after the supplied PDDL plan passes verification.

### 7. TravelPlanner is a separate non-PDDL pipeline

TravelPlanner does **not** use `BDIPlan`. Its active runtime is under `src/bdi_llm/travelplanner/`.

The flow is:
1. `travelplanner/adapter.py` converts the official sample into a `PlanningTask`
2. the adapter injects the output contract from `travelplanner/spec.md` into `domain_context`
3. `travelplanner/engine.py` generates a `TravelPlannerItinerary`
4. `travelplanner/serializer.py` converts it into official submission rows
5. `travelplanner/official.py` evaluates it with the official evaluator from the external TravelPlanner checkout (path from `TRAVELPLANNER_HOME`)
6. `travelplanner/runner.py` handles checkpointing, summaries, and optional MLflow logging

Repair is split into two layers:
- **non-oracle repair** uses deterministic local critique / patch guardrails from `travelplanner/review.py`
- **oracle repair** uses evaluator feedback during `bdi-repair` evaluation mode

`TRAVELPLANNER_BDI_PROMPT_VERSION` selects the BDI prompt stack in `travelplanner/engine.py`.
Current code defaults to `v3`; `v4` remains available as an experimental path.

### 8. Other active subsystems

- `scripts/replanning/run_dynamic_replanning.py` + `src/bdi_llm/dynamic_replanner/` — execution-aware replanning after grounded-action failure

## Data and artifact conventions

- `planbench_data/` — current PDDL benchmark assets and VAL binary
- TravelPlanner official checkout — external repo, NOT stored here; path supplied via `TRAVELPLANNER_HOME` or `--travelplanner_home`
- `runs/` — mutable checkpoints, scratch outputs, and MLflow data (`runs/mlflow/`)
- `artifacts/paper_eval_20260213/` — frozen paper evidence snapshot; do not edit or treat mutable reruns as replacements for paper numbers
- `RESULTS_PROVENANCE.md` — exact source files for every benchmark number in README; update when regenerating results

## Project automation and docs (non-runtime)

- `scripts/ralph/` — Ralph autonomous agent executor (PRD-driven task decomposition with quality gates)
- `paper_icml2026/` — ICML paper artifacts (figures, sections, compiled paper)
- `docs/conductor/` — documentation hub (product, workflow, tech stack, tracks)
- `docs/c4/` — C4 architecture diagrams (context, container, component)

## Known repo gotcha

PlanBench assets live at the repo root under `planbench_data/`. The `Dockerfile` correctly copies this root-level `planbench_data/` tree — that `COPY` directive is accurate. Any reference to `workspaces/planbench_data/` in older notes or scripts was the stale path; `planbench_data/` at the repo root is the canonical location.

## Bridges2 / PSC deployment lessons

These are the current known-good constraints and failure modes for running this
repo on PSC Bridges2.

### 1. Storage placement rules

- Treat `/ocean/projects/cis260113p/zjiang9/` as the only valid home for
  project environments, caches, logs, and mutable artifacts.
- Do **not** install project dependencies into `HOME` on Bridges2.
- Redirect at least these paths to `/ocean`:
  - `PIP_CACHE_DIR`
  - `CONDA_PKGS_DIRS`
  - `HF_HOME`
  - `HF_HUB_CACHE`
  - `TMPDIR`
  - `PYTHONUSERBASE`
- `HOME` on Bridges2 is quota-constrained; large `pip` / HF caches can fill it
  quickly and break installs with `Disk quota exceeded`.

### 2. Job partition split

- Environment creation / package installation should run on CPU partitions
  first, then model serving / eval should run on GPU partitions.
- For Bridges2 `RM-shared`, respect the partition's memory-per-core cap.
  Avoid requests whose implied memory-per-core exceeds `2000M/core`.
- When a workflow has a CPU setup phase and a GPU serve/eval phase, submit them
  as separate jobs with Slurm dependencies.

### 3. Git sync discipline

- When syncing work from local to the Bridges2 checkout, use Git only.
- Do **not** manually copy directories or overwrite the remote worktree outside
  Git.
- If the Bridges2 repo is already dirty, preserve unrelated changes and update
  only the intended paths via `git fetch` plus targeted checkout/stash flows.

### 4. GLM-4.7-Flash on Bridges2: host install findings

- `zai-org/GLM-4.7-Flash` does not work with older stable combinations such as
  `vllm 0.11.2 + transformers 4.57.x`; the model architecture
  `glm4_moe_lite` is not recognized there.
- Updating only `transformers` is insufficient; older `vllm` builds fail later
  on tokenizer/runtime compatibility.
- The Hugging Face model card recommendation (`vLLM` main/nightly +
  `transformers` main) is logically correct for model support, but **direct
  host-side deployment on Bridges2 fails for system reasons**:
  - host `glibc` is `2.28`
  - latest precompiled `vllm` components require newer `glibc`
  - newer stacks may also expect a newer NVIDIA driver than the host exposes
- In other words: on Bridges2, the blocker is not the model card itself, but
  the host runtime ABI / driver floor.

### 5. PSC-supported path that is most promising

- Prefer `Apptainer` / `Singularity` on Bridges2 for new LLM serving work.
- PSC officially supports these container workflows and provides NGC-backed
  containers under `/ocean/containers/`.
- For this repo, the most relevant current base image is:
  - `/ocean/containers/ngc/pytorch/pytorch_25.02-py3.sif`
- This image has a newer userspace (`glibc 2.39`) and was verified to expose
  the GPU successfully under `apptainer exec --nv`, including
  `torch.cuda.is_available() == True` on an H100 node.
- PSC's prebuilt AI module environments are currently too old for
  `GLM-4.7-Flash`, and the visible NIM catalog on Bridges2 is not a ready-made
  general LLM serving path for this model.

### 6. Current Bridges2 helper scripts

- Host-oriented scripts live under `bridges2_sbatch_under_review/`:
  - `psc_ocean_env.sh`
  - `install_bdi_llm.sbatch`
  - `run_eval_glm47flash_paperaligned.sbatch`
  - `aggregate_planbench_glm47flash_paperaligned.sbatch`
- Container-oriented scripts also live there:
  - `psc_apptainer_env.sh`
  - `install_glm47flash_apptainer.sbatch`

### 7. Operational gotchas from debugging

- Avoid expensive recursive size checks in job prologs on Bridges2; running
  `du -sh` on massive cache directories can stall short validation jobs.
  Bound such checks with `timeout` or skip them when they are not essential.
- Avoid deeply nested shell here-documents inside `apptainer ... bash -lc "..."`
  payloads. For inline verification code, prefer a temporary script file or
  `python -c` to avoid quoting bugs.

### 8. GLM-4.7-Flash 部署(2026-04-17 已验证可用)

- **部署说明书**: `docs/psc_glm47_deploy.md`(TL;DR + 坑 + 访问方式 + 参数解释)
- **工作脚本**:
  - `scripts/psc_deploy/serve_persistent.sh` — 长驻 server(持续 4h 供推理/eval)
  - `bridges2_sbatch_under_review/run_eval_glm47flash_paperaligned.sbatch` — RM-shared 单 domain paper-aligned eval
  - `bridges2_sbatch_under_review/aggregate_planbench_glm47flash_paperaligned.sbatch` — 聚合主表和附录表
- **持久资产**(不要重建,直接复用):
  - SIF: `/ocean/projects/cis260113p/zjiang9/apptainer/vllm_nightly.sif`(8.5 GB)
  - HF 权重: `/ocean/projects/cis260113p/zjiang9/hf_cache/hub/models--zai-org--GLM-4.7-Flash`(59 GB)
  - 运行时 cache: `/ocean/projects/cis260113p/zjiang9/vllm_runtime_cache`
- **7 个 cache env vars 必须全设**(`HF_HOME` / `HF_HUB_CACHE` / `VLLM_CACHE_ROOT` /
  `TRITON_CACHE_DIR` / `TORCHINDUCTOR_CACHE_DIR` / `XDG_CACHE_HOME` / `TMPDIR`),
  否则 jet/home 25GB quota 会在 torch.compile 阶段爆(`Errno 122 Disk quota exceeded`)。
- **镜像必须用 `vllm/vllm-openai:nightly`**,stable `latest` 缺 `glm4_moe_lite` 架构支持。
- **nightly 镜像漏装 pandas** → 脚本内已加 `pip install pandas pyarrow` + `--writable-tmpfs` 修复。
- Claude Code 全局 hook `~/.claude/hooks/psc_cache_guard.py` 会拦截 inline
  `apptainer exec` / `vllm serve` 缺 cache env vars 的命令。

### 9. GLM-4.7-Flash 官方 API 对齐部署 + 双 benchmark 评测(2026-04-18 已验证)

**顶层设计**: 4 个脚本构成最小闭环,缺一刀全链路断。

**4 个脚本对应职责**:

| 脚本 | 作用 |
|---|---|
| `scripts/psc_deploy/run_vllm_glm.sh` | vLLM 启动体,使用 `vllm/vllm-openai:latest` 镜像 + 7 个官方 flag + 全套 cache 重定向 |
| `scripts/psc_deploy/serve_glm_mtp.sbatch` | 4h GPU-shared sbatch wrapper(调用上面脚本)。`-A cis260113p` |
| `bridges2_sbatch_under_review/run_eval_glm47flash_travelplanner.sbatch` | TravelPlanner validation eval,RM-shared 8h,读 `BDI_SERVICE_READY_ENV_FILE` |
| `bridges2_sbatch_under_review/run_planbench_glm47flash.sbatch` | PlanBench paper-aligned eval,RM-shared 8h,读同一个 ready_env |

**官方 7 个必开 flag(任一不开 → 输出不对齐官方 API)**:

```
--tensor-parallel-size 1        (硬件约束,官方推荐 4)
--speculative-config.method mtp (MTP 投机解码加速,bit-wise 等价)
--speculative-config.num_speculative_tokens 1
--tool-call-parser glm47
--reasoning-parser glm45
--enable-auto-tool-choice
--served-model-name glm-4.7-flash  (注意有连字符,不是 glm47flash)
```

**提交 serve job(第一步,必须先于 eval)**:

```bash
cd /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver
sbatch scripts/psc_deploy/serve_glm_mtp.sbatch
# 等 3-5 min 模型 load + MTP compile
# 拿到节点:squeue -u $USER -o '%.10i %.25j %R' 看 NODELIST
# ready 指标:log 里出现 'Application startup complete' + 端口 8000
```

**ready_env 文件(每次换 serve 节点要更新)**:

位置: `/ocean/projects/cis260113p/zjiang9/runs/status/glm-4.7-flash_interactive_ready_env.sh`

```bash
export VLLM_HOST=<node_name>
export VLLM_PORT=8000
export OPENAI_API_BASE=http://<node_name>:8000/v1
export LLM_MODEL=openai/glm-4.7-flash
export MODEL_NAME=glm-4.7-flash
export MAX_MODEL_LEN_EFFECTIVE=65536
export SERVER_MANIFEST_PATH=/ocean/projects/cis260113p/zjiang9/runs/server_manifests/server_manifest_interactive_mtp.json
```

**提交 TravelPlanner eval**:

```bash
USER_SITE=/ocean/projects/cis260113p/zjiang9/python_user/lib/python3.12/site-packages
READY=/ocean/projects/cis260113p/zjiang9/runs/status/glm-4.7-flash_interactive_ready_env.sh
RUN_TAG=glm47flash_tp_apialign_$(date +%Y%m%d_%H%M)

sbatch --mem=15G \
  --export=ALL,RUN_TAG=$RUN_TAG,WORKERS=4,BDI_SERVICE_READY_ENV_FILE=$READY,LLM_MODEL=openai/glm-4.7-flash,PYTHONPATH=$USER_SITE \
  bridges2_sbatch_under_review/run_eval_glm47flash_travelplanner.sbatch
```

**提交 PlanBench eval**:

```bash
sbatch --export=ALL,RUN_TAG=glm47flash_pb_apialign_$(date +%Y%m%d_%H%M),WORKERS=4,BDI_SERVICE_READY_ENV_FILE=$READY,LLM_MODEL=openai/glm-4.7-flash,PYTHONPATH=$USER_SITE \
  bridges2_sbatch_under_review/run_planbench_glm47flash.sbatch
```

**关键 env var 约束**:

- `PYTHONPATH=$USER_SITE` 必传,否则 `ModuleNotFoundError: No module named 'dspy'`
- `LLM_ENABLE_THINKING=true` 已写死在 val sbatch,配合 `--reasoning-parser glm45` 让推理走 `reasoning_content` 字段
- RM-shared 有 `2000M/core` 内存上限,`--mem=15G` 对 8 cores 刚好(别用 16G)
- SLURM account `-A cis260113p`(不是 cis250019p,那只是文件路径)

**验收指标**:

- `silent_failure_rate = (template_echo + blank_submission) / total` 应 < 5%
- 若 > 10%,检查 parser flag 是否 1 个都没漏、`LLM_ENABLE_THINKING=true`、`served-model-name` 是否带连字符
- smoke test 应同时返回 `reasoning` 和 `content` 两个字段的 JSON

**常见坑**:

1. jet/home 25G quota 被 HF 下载打爆 → `SINGULARITYENV_HF_HOME` 重定向到 /ocean(`run_vllm_glm.sh` 内已处理)
2. `${SCRIPT_DIR}/../` 相对路径 source 在 SLURM 下失效(SLURM 会把 sbatch 复制到 `/var/spool/slurm/d/`) → 所有 source 路径必须绝对
3. Bridges2 login node 有多个(br001-br014),`ssh bridges2` 可能落到不同节点 → daemon/watchdog 不能靠 PID 杀,要把脚本本身 disable
4. `--served-model-name` 必须与 eval 端 `LLM_MODEL=openai/<name>` 一致,连字符都要对齐

### 10. GLM-4.7-Flash deployment 踩坑清单(2026-04-18 session)

接上节,本次 debug 踩的具体坑 + 根因 + 规避。

**坑 1: GPU-shared 节点 port 8000 被别的租户占用**
- 症状: `OSError: [Errno 98] Address already in use`
- 根因: GPU-shared 是多租户,同节点多用户共享端口空间;默认 port 8000 极易撞。  
  之前 interactive 成功是因为 salloc 挑到的节点恰好没人占 8000,纯运气。
- 规避: `run_vllm_glm.sh` 强制 `--port 47259`(不常见高位端口,私用范围)。
- 诊断抓手: vllm 启动 log 会打印 `non-default args: {...}`,  
  如果 `'port'` 字段缺席 = `--port` 没生效。

**坑 2: interactive session 默认 walltime 只有 1 小时**
- 症状: serve 跑到 1h 整点被 SLURM TIMEOUT 强制终止,eval 全失败。
- 规避: salloc 必须显式 `-t 08:00:00`;长跑用 sbatch GPU-shared(`serve_glm_mtp.sbatch` 的 4h)。

**坑 3: 文件分叉 — repo 改了但 sbatch exec 的是别处副本**
- 症状: 改了 `scripts/psc_deploy/run_vllm_glm.sh` 后重提 serve,依旧跑旧行为。
- 根因: sbatch 里写的是 `exec bash /ocean/projects/cis250019p/zjiang9/run_vllm_glm.sh`,  
  那是 repo 外的副本,repo 改动没同步过去。
- 规避: sbatch 统一 `exec bash <repo-absolute-path>/scripts/psc_deploy/run_vllm_glm.sh`,  
  不在 repo 外放任何可执行副本。

**坑 4: SLURM 提交时快照 sbatch 文件**
- 症状: `sbatch` 后再改 sbatch 内容,**对已提交的 job 不生效**。
- 根因: SLURM 在 sbatch 提交时把文件复制到 `/var/spool/slurm/d/job<N>/slurm_script`。
- 规避: 改完 sbatch 必须 scancel + 重提,不能 `scontrol update` 改 Command。

**坑 5: PSC 账号二元性 — filesystem vs compute allocation**
- Filesystem 在 `/ocean/projects/cis250019p/zjiang9/`(用户 home 所属 group)。
- Compute allocation 在 `cis260113p`(sbatch `-A cis260113p`)。
- 两者不互通,sbatch 用错 account → permission denied。

**坑 6: bridges2 login node 有多个(br001-br014)**
- `ssh bridges2` 每次可能落到不同 login node,`ps` 只看当前节点进程。
- watchdog/daemon 杀不干净要 **rename 脚本本身**(釜底抽薪),不能只靠 PID。

**坑 7: `SINGULARITYENV_*` 传 env var 到容器内**
- 宿主 export 的变量**不自动**传进 singularity 容器,必须用 `SINGULARITYENV_` 前缀。
- 也见 warning: `SINGULARITYENV_VLLM_CACHE_ROOT is set, but APPTAINERENV_VLLM_CACHE_ROOT is preferred` —  
  新版 apptainer 推荐 `APPTAINERENV_` 前缀,但老版 singularity-CE 仍识别 `SINGULARITYENV_`。二选一即可,不影响功能。

**坑 8: val_interact 的 silent failure 桶演化**
- 未开 parser: template_echo + JSONAdapter parse fail(17.5%)
- 开 parser 但 thinking=false: NoneType 错误(27.5%,content=null)
- 开 parser + thinking=true + 正确 served-model-name: 0-5% silent failure ✅
- 三步配置缺一不可,任何一个错都会有特征性失败模式。

**诊断复盘模板**(下次 debug 时按这个顺序排查):
1. 看 vllm log 最后 5 行 error → 定位最直接原因(bind/OOM/import)
2. 看 `non-default args:` → 验证你的 flag 真的传到 vllm 了
3. curl `/v1/models` → 验证端点起来且模型名字对
4. 发一次带推理的请求 → 验证 reasoning 和 content 字段分离
5. 看 eval checkpoint 的 error bucket 分布 → 定位 silent failure 模式
