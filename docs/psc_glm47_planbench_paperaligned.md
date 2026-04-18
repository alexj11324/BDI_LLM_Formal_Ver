# PSC Bridges2 上运行 GLM-4.7-Flash PlanBench 论文对齐评测

这份文档只保留当前支持的主线路径：

1. `GPU-shared` 只负责跑常驻 GLM-4.7-Flash 推理服务
2. `RM-shared` 只负责跑 `paperaligned` 单 domain eval 和聚合 job
3. 所有持久化写路径都落在 `/ocean/projects/cis260113p/zjiang9/`

仓库中的 GLM-4.7-Flash 评测只保留这条主线，不再维护其他旁路。

## 支持的脚本

### GPU 侧

- [scripts/psc_deploy/serve_persistent.sh](../scripts/psc_deploy/serve_persistent.sh)
  作用：启动常驻 GLM 推理服务，自动尝试 `202752 -> 131072 -> 65536` 的 `max-model-len` 回退链，并写出：
  - `serve_<JOBID>_access.txt`
  - `glm47flash_service_ready_env.sh`
  - `server_manifest_<JOBID>.json`

### RM 侧

- [bridges2_sbatch_under_review/run_eval_glm47flash_paperaligned.sbatch](../bridges2_sbatch_under_review/run_eval_glm47flash_paperaligned.sbatch)
  作用：单个 domain 的 RM 评测 job。固定调用：
  `python scripts/evaluation/run_planbench_paperaligned.py --execution_mode bdi-repair --deterministic`

- [bridges2_sbatch_under_review/aggregate_planbench_glm47flash_paperaligned.sbatch](../bridges2_sbatch_under_review/aggregate_planbench_glm47flash_paperaligned.sbatch)
  作用：读取五个 domain 的结果，生成 paper 主表和附录表。

- [scripts/evaluation/aggregate_planbench_paper_tables.py](../scripts/evaluation/aggregate_planbench_paper_tables.py)
  作用：把五个 domain 的 `summary` 聚合成：
  - `pddl_results_glm47flash_table.json`
  - `pddl_results_glm47flash_table.tex`
  - `pddl_appendix_glm47flash_table.tex`
  - `aggregate_manifest.json`

## 路径约定

默认项目根路径：

```bash
export BDI_PROJECT_ROOT=/ocean/projects/cis260113p/zjiang9
export BDI_REPO_ROOT=/ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver
```

关键输出目录：

- GPU 就绪文件：
  `$BDI_STATUS_ROOT/glm47flash_service_ready_env.sh`
- GPU manifest：
  `$BDI_RUN_ROOT/server_manifests/`
- Domain 结果：
  `$BDI_RUN_ROOT/<RUN_TAG>/<DOMAIN>/`
- 聚合表：
  `$BDI_TABLE_ROOT/<RUN_TAG>/`
- SLURM 日志：
  `$BDI_SLURM_LOG_ROOT/`

## 0. 预检

先确认 PSC 上的 repo 在 `/ocean`，而不是 `HOME`：

```bash
ssh bridges2
cd /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver
git status --short
```

如果缺环境依赖，先用现有安装脚本在 `RM-shared` 上补环境：

```bash
cd /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver
sbatch bridges2_sbatch_under_review/install_bdi_llm.sbatch
```

## 1. 启动 GPU 推理服务

提交长驻服务：

```bash
cd /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver
sbatch scripts/psc_deploy/serve_persistent.sh
```

查 job：

```bash
squeue -u "$USER"
```

服务启动成功后，会写两个最重要的文件：

```bash
cat "${BDI_REPO_ROOT}/logs/serve_<JOBID>_access.txt"
cat "${BDI_STATUS_ROOT}/glm47flash_service_ready_env.sh"
```

`glm47flash_service_ready_env.sh` 至少会包含：

```bash
export VLLM_HOST=<node>
export VLLM_PORT=<port>
export OPENAI_API_BASE=http://<node>:<port>/v1
export LLM_MODEL=openai/glm47flash
export MAX_MODEL_LEN_EFFECTIVE=<202752_or_131072_or_65536>
export SERVER_MANIFEST_PATH=/ocean/.../server_manifest_<JOBID>.json
```

## 2. 提交单个 domain 的 RM 评测 job

默认模式是：

- `RM-shared`
- 不申请 GPU
- 固定 `--execution_mode bdi-repair`
- 固定 `--deterministic`
- 固定禁用 repair cache 和 early exit

先跑一个 dry-run：

```bash
cd /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver
sbatch --export=ALL,DOMAIN=blocksworld,MAX_INSTANCES=20,RUN_TAG=glm47flash_eval_dryrun_$(date +%Y%m%d) \
  bridges2_sbatch_under_review/run_eval_glm47flash_paperaligned.sbatch
```

全量跑某个 domain：

```bash
cd /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver
sbatch --export=ALL,DOMAIN=logistics,RUN_TAG=glm47flash_eval_$(date +%Y%m%d) \
  bridges2_sbatch_under_review/run_eval_glm47flash_paperaligned.sbatch
```

五个 domain 逐个提交：

```bash
cd /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver
RUN_TAG=glm47flash_eval_$(date +%Y%m%d)

for DOMAIN in \
  blocksworld \
  logistics \
  depots \
  obfuscated_deceptive_logistics \
  obfuscated_randomized_logistics
do
  sbatch --export=ALL,DOMAIN=${DOMAIN},RUN_TAG=${RUN_TAG} \
    bridges2_sbatch_under_review/run_eval_glm47flash_paperaligned.sbatch
done
```

## 3. 为什么只跑一次 `bdi-repair`

这套 runner 的 `bdi-repair` 模式会在同一次 run 里同时产出：

- `baseline_result`
- `bdi_initial_result`
- `bdi_repair_result`

所以不用再把 `Baseline`、`BDI`、`BDI-Repair` 拆成 3 次作业。

## 4. 结果文件怎么看

单个 domain 跑完后，结果目录大致长这样：

```text
/ocean/projects/cis260113p/zjiang9/runs/<RUN_TAG>/<DOMAIN>/
  checkpoint_<domain>_pipeline.json
  results_<domain>_bdi-repair_<timestamp>.json
  run_manifest_<domain>.json
```

其中：

- `results_*.json`
  是原始 paper-aligned runner 结果，包含每题的 `baseline_result`、`bdi_initial_result`、`bdi_repair_result`
- `checkpoint_*.json`
  是运行中间态
- `run_manifest_<domain>.json`
  是本次 domain 级 provenance，包括 deterministic、cache 开关、服务 manifest 路径等

## 5. 聚合成论文表格

等五个 domain 都跑完后，提交汇总 job：

```bash
cd /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver
RUN_TAG=glm47flash_eval_$(date +%Y%m%d)
sbatch --export=ALL,RUN_TAG=${RUN_TAG} \
  bridges2_sbatch_under_review/aggregate_planbench_glm47flash_paperaligned.sbatch
```

汇总 job 会输出到：

```text
/ocean/projects/cis260113p/zjiang9/runs/tables/<RUN_TAG>/
  aggregate_manifest.json
  pddl_results_glm47flash_table.json
  pddl_results_glm47flash_table.tex
  pddl_appendix_glm47flash_table.tex
```

用途：

- `pddl_results_glm47flash_table.tex`
  对齐 paper 主表 `Domain | N | Baseline | BDI | BDI-Repair`
- `pddl_appendix_glm47flash_table.tex`
  对齐 appendix 的绝对数表
- `pddl_results_glm47flash_table.json`
  机器可读版本
- `aggregate_manifest.json`
  聚合 provenance

## 6. 建议的实际执行顺序

1. `sbatch scripts/psc_deploy/serve_persistent.sh`
2. 先提 `blocksworld` dry-run：
   `MAX_INSTANCES=20`
3. 检查 dry-run 结果
4. 再顺序提五个全量 domain
5. 五个都完成后跑聚合 job

## 7. 停服务

```bash
scancel <GPU_SERVER_JOBID>
```

## 8. 目前默认值

- `LLM_TEMPERATURE=0.0`
- `LLM_SEED=42`
- `LLM_ENABLE_THINKING=true`
- `LLM_MAX_TOKENS=32768`
- `RM-shared` 评测资源：
  - `--cpus-per-task=8`
  - `--mem=16G`
- `max-model-len` 回退链：
  - `202752`
  - `131072`
  - `65536`

## 9. 已知注意事项

- 这套文档假设 GPU 服务是单实例长驻，然后 RM job 通过 `OPENAI_API_BASE` 去调用它。
- 默认不并行压同一个 GPU 服务；五个 domain job 建议顺序提交。
- 论文主结果默认以 deterministic 路径定义，不以多线程高并发路径定义。
- 如果服务 job 重新启动，记得重新读取 `glm47flash_service_ready_env.sh`；RM 作业会自动 source 最新文件。
