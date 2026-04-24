---
description: Detailed PSC Bridges2 deployment SOPs (GLM-4.7-Flash, Qwen3.6, debugging gotchas). Loaded automatically alongside CLAUDE.md.
---

# PSC Bridges2 Deployment SOPs

> Extracted from CLAUDE.md to keep the main file lean. Subsections 1-6 of "Bridges2 / PSC deployment lessons" remain in CLAUDE.md (storage rules, partition split, git sync, GLM host findings, supported paths, helper scripts). This file holds the deeper SOPs and debugging gotchas.

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
| `scripts/psc_deploy/glm47/run_vllm.sh` | vLLM 启动体,使用 `vllm/vllm-openai:latest` 镜像 + 7 个官方 flag + 全套 cache 重定向 |
| `scripts/psc_deploy/glm47/serve.sbatch` | 4h GPU-shared sbatch wrapper(调用上面脚本)。`-A cis260113p` |
| `scripts/psc_deploy/glm47/eval_travelplanner.sbatch` | TravelPlanner validation eval,RM-shared 8h,读 `BDI_SERVICE_READY_ENV_FILE` |
| `scripts/psc_deploy/glm47/eval_planbench.sbatch` | PlanBench paper-aligned eval,RM-shared 8h,读同一个 ready_env |

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
sbatch scripts/psc_deploy/glm47/serve.sbatch
# 等 3-5 min 模型 load + MTP compile
# 拿到节点:squeue -u $USER -o '%.10i %.25j %R' 看 NODELIST
# ready 指标:log 里出现 'Application startup complete' + 端口 47259(见 run_vllm_glm.sh)
```

**ready_env 文件(每次换 serve 节点要更新)**:

位置: `/ocean/projects/cis260113p/zjiang9/runs/status/glm-4.7-flash_interactive_ready_env.sh`

```bash
export VLLM_HOST=<node_name>
export VLLM_PORT=47259
export OPENAI_API_BASE=http://<node_name>:47259/v1
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
  scripts/psc_deploy/glm47/eval_travelplanner.sbatch
```

**提交 PlanBench eval**:

```bash
sbatch --export=ALL,RUN_TAG=glm47flash_pb_apialign_$(date +%Y%m%d_%H%M),WORKERS=4,BDI_SERVICE_READY_ENV_FILE=$READY,LLM_MODEL=openai/glm-4.7-flash,PYTHONPATH=$USER_SITE \
  scripts/psc_deploy/glm47/eval_planbench.sbatch
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
- 症状: 改了 `scripts/psc_deploy/glm47/run_vllm.sh` 后重提 serve,依旧跑旧行为。
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

### 11. Qwen3.6-35B-A3B 部署 + dual benchmark (与 GLM-4.7-Flash 并列可选)

Model folder layout (每个模型自包含,scripts 不混):

```
scripts/psc_deploy/
├── glm47/             # GLM-4.7-Flash
│   ├── run_vllm.sh
│   ├── run_interactive.sh
│   ├── serve.sbatch
│   ├── eval_travelplanner.sbatch
│   ├── eval_travelplanner_test.sbatch
│   └── eval_planbench.sbatch
└── qwen36/            # Qwen3.6-35B-A3B
    ├── run_vllm.sh
    ├── serve.sbatch
    ├── eval_travelplanner.sbatch
    └── eval_planbench.sbatch
```

**Qwen3.6 official flags (差异于 GLM)**:
- `--reasoning-parser qwen3` (而非 glm45)
- `--tool-call-parser qwen3_coder` (而非 glm47)
- `--speculative-config '{"method":"qwen3_next_mtp","num_speculative_tokens":2}'` (JSON 格式,与 GLM MTP 语法不同)
- `--language-model-only` (text-only mode,skip vision encoder,省显存)
- `--max-model-len 32768` (35B 在 80GB 上 context 要降)
- `--served-model-name qwen3.6-35b-a3b`
- 端口 47260 (避开 GLM 的 47259)

**提交 Qwen3.6 完整 pipeline**:

```bash
cd /ocean/projects/cis260113p/zjiang9/repo/BDI_LLM_Formal_Ver

# Step 1: serve
sbatch scripts/psc_deploy/qwen36/serve.sbatch

# Step 2: 写 ready_env 到 status/qwen3.6-35b-a3b_ready_env.sh (参考 GLM 格式,端口 47260)

# Step 3: eval (并行 TP + PlanBench)
USER_SITE=/ocean/projects/cis260113p/zjiang9/python_user/lib/python3.12/site-packages
READY=/ocean/projects/cis260113p/zjiang9/runs/status/qwen3.6-35b-a3b_ready_env.sh
TAG=qwen36_$(date +%Y%m%d_%H%M)

sbatch --export=ALL,RUN_TAG=$TAG,WORKERS=4,BDI_SERVICE_READY_ENV_FILE=$READY,LLM_MODEL=openai/qwen3.6-35b-a3b,PYTHONPATH=$USER_SITE \
  scripts/psc_deploy/qwen36/eval_travelplanner.sbatch

sbatch --export=ALL,RUN_TAG=$TAG,WORKERS=4,BDI_SERVICE_READY_ENV_FILE=$READY,LLM_MODEL=openai/qwen3.6-35b-a3b,PYTHONPATH=$USER_SITE \
  scripts/psc_deploy/qwen36/eval_planbench.sbatch
```

**两模型并存**: GLM 可以 47259 + Qwen 47260 同节点运行(显存够的话),或分两个 serve job 到不同节点。eval sbatch 通过 ready_env 指向不同 endpoint 即可切换模型。
