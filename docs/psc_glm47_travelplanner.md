# PSC Bridges2 上运行 GLM-4.7-Flash × TravelPlanner 评测

这份文档覆盖 GLM-4.7-Flash 在 Bridges2 上跑完整 TravelPlanner 复现流程，包括 validation（N=180，三种 mode）和 test 提交（N=1,000）。

论文目前 TravelPlanner 部分（`paper_icml2026/paper/paper/sections/travelplanner_results.tex`）只报告了 GPT-5 结果；本流程为修订版提供 GLM-4.7-Flash 多模型对比数据。

涉及三个 sbatch 脚本（均在 `bridges2_sbatch_under_review/`）：

| 脚本 | 用途 |
|------|------|
| `setup_travelplanner_deps.sbatch` | 一次性依赖安装（clone + HF 数据集预取 + 验证） |
| `run_eval_glm47flash_travelplanner.sbatch` | RM-shared validation 评测（N=180，3 种 mode） |
| `run_eval_glm47flash_travelplanner_test.sbatch` | RM-shared test 提交（N=1,000，leaderboard 上传） |

GPU 推理服务统一使用 `scripts/psc_deploy/serve_persistent.sh`，不在此重复介绍，所有 GPU server 细节（Apptainer、cache env vars、max-model-len 回退链、SU 消耗）见 `docs/psc_glm47_deploy.md`。

---

## 1. 前置条件

### GPU 推理服务

本流程需要 GLM-4.7-Flash 推理服务处于 RUNNING 状态。所有 server 部署细节统一参见：

> [docs/psc_glm47_deploy.md](./psc_glm47_deploy.md)

### TravelPlanner 专用前置条件

以下三项是 TravelPlanner 流程额外需要的，PlanBench 流程不依赖它们：

1. **TravelPlanner 官方 repo**：需要 clone 到 `${BDI_PROJECT_ROOT}/TravelPlanner_official`（`BDI_PROJECT_ROOT` 默认为 `/ocean/projects/cis260113p/zjiang9`）。
   - 关键文件：`evaluation/eval.py`（被 `src/bdi_llm/travelplanner/official.py` 调用）
   - 数据库文件：`database/poi_detail.csv`、`flight.csv`、`google_distance_matrix.csv`、`attraction.csv`、`accommodations.csv`

2. **HuggingFace 数据集预取**：`osunlp/TravelPlanner` 的 validation 和 test split 必须预取到 `${HF_HOME}`（默认 `/ocean/projects/cis260113p/zjiang9/hf_cache`）。
   - 注意：生产评测 job 会设置 `HF_DATASETS_OFFLINE=1`，在计算节点上无法在线下载，必须提前缓存。

3. **HF_TOKEN**（仅 test 提交需要）：用于向 HuggingFace leaderboard 上传 test 结果。Validation 不需要。

---

## 2. 一次性 setup

以下命令只需在首次使用前跑一次。如果 `${BDI_PROJECT_ROOT}/TravelPlanner_official` 已存在且数据集已缓存，可跳过。

```bash
cd /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver
sbatch bridges2_sbatch_under_review/setup_travelplanner_deps.sbatch
```

**该 job 做了什么：**

1. **Clone TravelPlanner repo**：`git clone --depth 1 https://github.com/OSU-NLP-Group/TravelPlanner.git ${TP_DIR}`（如目录已存在则跳过）。
2. **验证数据库文件**：检查 5 个核心 CSV 文件是否存在，缺失时打印警告（不报错退出，避免阻塞，但缺失文件会导致后续 eval 失败）。
3. **验证 eval.py**：确认 `evaluation/eval.py` 存在，若缺失则直接 exit 1。
4. **预取 HuggingFace 数据集**：临时取消 `HF_DATASETS_OFFLINE=1`，调用 `load_dataset("osunlp/TravelPlanner", ...)` 写入 `${HF_HOME}`。
5. **存储快照**：打印 TravelPlanner 目录大小和 HF_HOME 大小。

**验证 setup 成功：**

```bash
# 查看 job 输出
cat /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver/logs/slurm/glm47_tp_setup_<JOBID>.out

# 确认关键文件存在
ls /ocean/projects/cis260113p/zjiang9/TravelPlanner_official/evaluation/eval.py
ls /ocean/projects/cis260113p/zjiang9/TravelPlanner_official/database/
```

输出末尾应显示 `=== Setup complete ===`，且 5 个数据库文件均显示 `FOUND`。

---

## 3. Validation 跑（N=180，三种 mode）

```bash
cd /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver

# 如果 GPU server 尚未启动：
sbatch scripts/psc_deploy/serve_persistent.sh

# 等 server 进入 RUNNING 状态后提交 RM eval job：
sbatch --export=ALL,RUN_TAG=glm47flash_tp_val_$(date +%Y%m%d),WORKERS=16 \
  bridges2_sbatch_under_review/run_eval_glm47flash_travelplanner.sbatch
```

**该 job 做了什么：**

调用 `run_travelplanner_release_matrix.py --run-validation`，内部依次串行跑三种 mode：

1. `baseline`（直接 LLM 生成）
2. `bdi`（BDI 结构化生成 + domain-context 注入）
3. `bdi-repair`（完整流程含非 oracle 修复）

三种 mode 在同一 job 内完成，不需要拆成 3 个 job。每种 mode 结果独立写出，中间态 checkpoint 支持重启后断点续跑。

**壁钟时间估算：**

8 小时 walltime 覆盖 180 × 3 mode，`WORKERS=16` 并发。如推理服务响应慢可适当降低到 `WORKERS=8`。

**检查 server 状态的快速方法：**

```bash
# server ready env 文件写盘后才能提交 eval job
cat /ocean/projects/cis260113p/zjiang9/runs/status/glm47flash_service_ready_env.sh
# 等价形式：cat ${BDI_RUN_ROOT}/status/glm47flash_service_ready_env.sh
```

---

## 3.5. 防 stale ready-env（提交 eval job 前必读）

### 为什么有这个问题

`glm47flash_service_ready_env.sh` 是持久化文件，不会随 server job 结束自动删除。如果之前的 server job 留下了旧的 ready-env，步骤 3 中的 `while [ ! -f "$READY_ENV" ]` 循环会立即退出（文件已存在），然后 eval job 拿着**过期的 `OPENAI_API_BASE`**（旧 job 的 host:port）去连接，`wait_for_openai_compat` 超时失败，eval job 报 `Server not ready within 120s` 退出。

### 缓解措施

**第一步（在提交 serve job 之前）**：先清理旧的 ready-env 文件，避免新 eval job 读到旧地址：

```bash
READY_ENV="${BDI_RUN_ROOT}/status/glm47flash_service_ready_env.sh"
# 等价绝对路径：/ocean/projects/cis260113p/zjiang9/runs/status/glm47flash_service_ready_env.sh
rm -f "$READY_ENV"
# 然后再提交 serve job：
sbatch scripts/psc_deploy/serve_persistent.sh
```

**第二步（等 ready-env 写盘之后、提交 eval job 之前）**：source ready-env 并对推理服务做连通性验证，确认真正可达再提交 eval：

```bash
source "$READY_ENV"
SERVE_OK=0
for i in 1 2 3 4 5 6; do
  if curl -fsS "${OPENAI_API_BASE}/models" >/dev/null; then
    echo "serve verified"; SERVE_OK=1; break
  fi
  echo "serve not ready, retry $i"; sleep 20
done
if [ "$SERVE_OK" -ne 1 ]; then
  echo "ERROR: serve unreachable after 6 retries" >&2
  exit 1
fi
# 验证通过后再提交 eval job：
sbatch --export=ALL,RUN_TAG=glm47flash_tp_val_$(date +%Y%m%d),WORKERS=16 \
  bridges2_sbatch_under_review/run_eval_glm47flash_travelplanner.sbatch
```

6 次 × 20s = 最多等待 2 分钟。如果全部 curl 失败则 `exit 1` fail-closed，**不继续提交 eval job**，避免浪费 SU 配额在一个不可能成功的评测上。

---

## 4. Test 提交（N=1,000）

```bash
cd /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver

sbatch --export=ALL,RUN_TAG=glm47flash_tp_test_$(date +%Y%m%d),WORKERS=16,HF_TOKEN=${HF_TOKEN} \
  bridges2_sbatch_under_review/run_eval_glm47flash_travelplanner_test.sbatch
```

**该 job 做了什么：**

调用 `run_travelplanner_release_matrix.py --run-test`，内部对 `baseline`、`bdi`、`bdi-repair` 三种 mode 分别跑 `run_travelplanner_test_submit.py`，生成符合官方格式的 JSONL，然后调用 `submit_to_leaderboard.py` 向 HuggingFace leaderboard 上传，需要有效的 `HF_TOKEN`。

**壁钟时间：** 12 小时，`WORKERS=16`。

---

## 5. 聚合 paper validation table

Validation job（Step 3）跑完后，用以下命令提交聚合 job，生成论文 Table 3：

```bash
AGG_JOB=$(sbatch --parsable \
  --dependency=afterok:${VAL_JOB} \
  --export=ALL,RUN_TAG=${RUN_TAG} \
  bridges2_sbatch_under_review/aggregate_travelplanner_paperaligned.sbatch)
echo "Aggregate job: ${AGG_JOB}"
```

`VAL_JOB` 是步骤 3 提交 validation sbatch 时拿到的 job ID（`sbatch --parsable` 返回纯数字 ID）。

**为什么用 `afterok` 而非 `afterany`：**

Validation job 即使中途失败，已完成的 instance 结果仍残留在磁盘。聚合脚本使用 `OFFICIAL_DENOMINATORS`（validation N=180），对部分数据聚合会产生误导性的 Table 3（分母固定，分子偏低）。`afterok` 保证 180 × 3 mode 全部干净完成后才触发聚合，避免将不完整数据写入论文表格。

> **进一步的完整性保护**：聚合脚本会在读取结果后强制检查每个 mode 行数是否等于 180；任一 mode 不足 180 行会直接 `ValueError` 退出，不写出表格，避免半成品结果污染表格。

**Test job 失败不影响本步骤：**

聚合脚本只读取 `${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner/validation/`，与 test submission 目录完全独立。Test job 失败不会影响 validation table 的生成。

**输出文件：**

```text
${BDI_TABLE_ROOT}/${RUN_TAG}/travelplanner/
  tp_validation_table.tex          # 论文 Table 3 LaTeX 格式
  tp_validation_table.json         # 同内容 JSON，便于程序读取
  tp_aggregate_manifest.json       # 聚合元数据（run tag、时间戳、实例数等）
```

`BDI_TABLE_ROOT` 默认为 `${BDI_RUN_ROOT}/tables`（即 `/ocean/projects/cis260113p/zjiang9/runs/tables`）。

> **Test table 聚合本 plan 不做**。本地 `test_submit/` 目录只有平铺的 `checkpoint_<mode>.json` / `diagnostics_<mode>.json` / `submission_<mode>.jsonl` / `test_soleplanning_<mode>.jsonl`，没有 `results_travelplanner_*.json`。paper test table 的数字来自官方 leaderboard 返回（`leaderboard_results.json`），schema 对齐和聚合逻辑留作后续 follow-up。

---

## 6. Output 布局

### Validation

```text
${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner/
  validation/
    baseline/
      results_*.json
      submission_*.jsonl
      checkpoint_*.json
    bdi/
      results_*.json
      submission_*.jsonl
      checkpoint_*.json
    bdi-repair/
      results_*.json
      submission_*.jsonl
      checkpoint_*.json
  release_matrix_<stamp>.json
```

### Test

```text
${BDI_RUN_ROOT}/${RUN_TAG}/travelplanner_test/
  test_submit/
    checkpoint_baseline.json
    checkpoint_bdi.json
    checkpoint_bdi-repair.json
    diagnostics_baseline.json
    diagnostics_bdi.json
    diagnostics_bdi-repair.json
    submission_baseline.jsonl
    submission_bdi.jsonl
    submission_bdi-repair.jsonl
    test_soleplanning_baseline.jsonl
    test_soleplanning_bdi.jsonl
    test_soleplanning_bdi-repair.jsonl
    leaderboard_results.json          # 若 leaderboard 成功上传
  release_matrix_<stamp>.json         # 进程元数据汇总（不含指标数字）
```

> **注意**：test_submit 目录**是平铺的,没有 per-mode 子目录**——三个 mode 的 checkpoint / diagnostics / submission / test_soleplanning 文件通过文件名 mode 后缀区分(`checkpoint_baseline.json`、`checkpoint_bdi.json`、`checkpoint_bdi-repair.json` 共存于 `test_submit/` 下),由 `run_travelplanner_test_submit.py:89` 和 `run_travelplanner_release_matrix.py:115` 决定。test_submit **没有** `results_*.json`,因为 test 数据集没有公开标注,无法在本地计算 5 指标 + Final Pass Rate。paper test table 的数字来自官方 leaderboard 返回(`leaderboard_results.json`),schema 对齐和聚合逻辑留作后续 follow-up。

### Slurm 日志

```text
logs/slurm/
  glm47_tp_val_<JOBID>.out
  glm47_tp_val_<JOBID>.err
  glm47_tp_test_<JOBID>.out
  glm47_tp_test_<JOBID>.err
```

### 文件说明

| 文件 | 出现位置 | 内容 |
|------|----------|------|
| `results_*.json` | validation 各 mode 子目录 | 每条 instance 的完整评测结果（5 个指标 + Final Pass Rate） |
| `submission_*.jsonl` | validation 和 test 各 mode 子目录 | 官方格式提交文件（`idx`、`query`、`plan` 字段） |
| `checkpoint_*.json` | validation 和 test 各 mode 子目录 | 运行中间态，支持断点续跑 |
| `diagnostics_*.json` | test 各 mode 子目录 | 实例级错误/超时统计 |
| `test_soleplanning_*.jsonl` | test 各 mode 子目录 | 官方 leaderboard 上传格式（soleplanning split） |
| `release_matrix_<stamp>.json` | travelplanner / travelplanner_test 根 | 三种 mode 的汇总 + 元数据（prompt_version、workers、walltime 等） |

---

## 7. 已知坑与排障

### `LLM_ENABLE_THINKING=false` 强制覆盖

TravelPlanner eval sbatch 已在脚本内显式设置 `LLM_ENABLE_THINKING=false`，覆盖 `bdi_env.env` 的默认值。原因：nightly 镜像对 GLM thinking header 支持不一致，在 TravelPlanner 长上下文场景下会引发格式解析错误。**不要手动传 `LLM_ENABLE_THINKING=true`。**

### `TravelPlannerSetupError`

症状：eval job 启动后立即报错并退出。

可能原因：

- `TRAVELPLANNER_HOME` 指向的目录不存在或 clone 不完整
- `evaluation/eval.py` 缺失

修复：重新跑 setup sbatch，检查 job 输出确认所有文件 `FOUND`：

```bash
cat logs/slurm/glm47_tp_setup_<JOBID>.out | grep -E 'FOUND|MISSING|ERROR'
```

### `Server not ready within 120s`

症状：RM eval job 启动后等待推理服务超时退出。

修复步骤：

1. 检查 GPU server job 状态：`squeue -u $USER`
2. 如果 server 不在 RUNNING：先提交 `sbatch scripts/psc_deploy/serve_persistent.sh`，等待进入 RUNNING
3. 确认 ready 文件已写盘：`ls /ocean/projects/cis260113p/zjiang9/runs/status/glm47flash_service_ready_env.sh`（即 `${BDI_RUN_ROOT}/status/glm47flash_service_ready_env.sh`）
4. 重新提交 RM eval job

### `WORKERS` 上限

`WORKERS` 受推理服务 `--max-num-seqs` 限制。起步 `WORKERS=16`，如出现大量请求超时（`LLM_TIMEOUT=900`），降到 `WORKERS=8`。TravelPlanner 请求比 PlanBench 更长（多日行程），单请求耗时约 30-120s，实际并发效果低于 PlanBench。

### `HF_DATASETS_OFFLINE=1` 导致数据集加载失败

生产 eval job 默认开启 `HF_DATASETS_OFFLINE=1`。如果 dataset 未预取，会报 `ConnectionError: Offline mode is enabled`。

修复：运行 setup sbatch（步骤 2）预取数据集，不要在 eval job 内试图在线下载。

---

## 8. 与 PlanBench 的关系

本流程和 PlanBench 论文对齐评测（见 `docs/psc_glm47_planbench_paperaligned.md`）共用同一个 GPU server 实例（`serve_persistent.sh`），不需要分别启动。

**推荐执行顺序（单次 server 会话内）：**

```bash
# 1. 启动 GPU server（4h walltime）
sbatch scripts/psc_deploy/serve_persistent.sh

# 2. 等 server RUNNING 后，先跑 PlanBench（单 domain 约 2-3h，可并行提交五个 domain）
RUN_TAG=glm47flash_eval_$(date +%Y%m%d)
for DOMAIN in blocksworld logistics depots obfuscated_deceptive_logistics obfuscated_randomized_logistics; do
  sbatch --export=ALL,DOMAIN=${DOMAIN},RUN_TAG=${RUN_TAG} \
    bridges2_sbatch_under_review/run_eval_glm47flash_paperaligned.sbatch
done

# 3. 同时或之后跑 TravelPlanner validation（约 4-8h）
sbatch --export=ALL,RUN_TAG=glm47flash_tp_val_$(date +%Y%m%d),WORKERS=16 \
  bridges2_sbatch_under_review/run_eval_glm47flash_travelplanner.sbatch
```

如 4h server walltime 不够覆盖全部 job，重新提交一次 server job 再跑 test submission 即可；RM eval job 通过 `glm47flash_service_ready_env.sh` 自动读取最新的 `OPENAI_API_BASE`，不需要手动改任何参数。

**并行说明：** 多个 RM 评测 job 可以同时向同一个 GPU server 发请求，`WORKERS` 控制客户端并发数，server 内部通过批处理调度处理，不会造成 server 崩溃。
