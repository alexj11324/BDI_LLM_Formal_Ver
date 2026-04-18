# PSC Bridges2 上部署 GLM-4.7-Flash (vLLM + Apptainer)

**验证日期**: 2026-04-17
**节点**: w001 (1× H100-80GB)
**项目**: `cis260113p`

---

## TL;DR — 两步跑通

```bash
# 1. 上传脚本(只需做一次)
scp scripts/psc_deploy/*.sh bridges2:/ocean/projects/cis260113p/zjiang9/scripts/
# 若 scp 挂(sftp disabled),改用:
#   cat scripts/psc_deploy/serve_persistent.sh | ssh bridges2 'cat > /ocean/projects/cis260113p/zjiang9/scripts/serve_persistent.sh'

# 2. 提交长驻 server(4h)
ssh bridges2 "cd /ocean/projects/cis260113p/zjiang9/scripts && sbatch serve_persistent.sh"

# 3. 查 server 状态(等到 RUNNING)
ssh bridges2 'squeue -u $USER'

# 4. 拿连接信息(job RUNNING 后生成)
ssh bridges2 'cat /ocean/projects/cis260113p/zjiang9/logs/serve_<JOBID>_access.txt'
```

---

## 关键资产位置

| 文件 | PSC 位置 | 作用 |
|------|----------|------|
| `vllm_nightly.sif` | `/ocean/projects/cis260113p/zjiang9/apptainer/` (8.5 GB) | vLLM nightly 镜像,**首次 pull 后持久复用** |
| GLM-4.7-Flash 权重 | `/ocean/projects/cis260113p/zjiang9/hf_cache/hub/models--zai-org--GLM-4.7-Flash/` (59 GB) | HF 缓存 |
| Runtime cache | `/ocean/projects/cis260113p/zjiang9/vllm_runtime_cache/` | torch.compile / triton / inductor 编译缓存,warm start 用 |
| 访问说明 | `/ocean/projects/cis260113p/zjiang9/logs/serve_<JOBID>_access.txt` | 每次启动自动写入 host:port |
| 本 repo 脚本 | `scripts/psc_deploy/` | 部署验证 + 长驻 server |

---

## 调用 server(服务器 RUNNING 后)

### 方式 1: 在 PSC 内调用(login 或 compute node)
```bash
curl http://<NODE>:<PORT>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"glm47flash","messages":[{"role":"user","content":"hello"}]}'
```

### 方式 2: SSH tunnel 从本地调用
```bash
ssh -L <PORT>:<NODE>:<PORT> bridges2
# 本地另开终端:
curl http://localhost:<PORT>/v1/chat/completions ...
```

### 方式 3: OpenAI Python SDK
```python
from openai import OpenAI
client = OpenAI(base_url=f"http://{NODE}:{PORT}/v1", api_key="dummy")
resp = client.chat.completions.create(
    model="glm47flash",
    messages=[{"role": "user", "content": "hello"}],
)
```

`<NODE>` 和 `<PORT>` 从 `access.txt` 取。

### 停 server
```bash
ssh bridges2 "scancel <JOBID>"
```

---

## 踩过的坑(按顺序)

| 坑 | 根因 | 修复 |
|----|------|------|
| **1. `glm4_moe_lite` 不识别** | `vllm/vllm-openai:latest` stable 不支持 GLM-4.7 | 改用 `:nightly` tag |
| **2. `No module named 'pandas'`** | nightly 镜像漏装 pandas | `--writable-tmpfs` + 启动前 `pip install pandas pyarrow` |
| **3. `Errno 122 Disk quota exceeded` (torch.compile)** | vLLM 默认写 `~/.cache/vllm/`,jet/home 25GB 爆 | **7 个 cache env vars 全部重定向到 Ocean** (见下) |

### 必备的 7 个 env vars(`serve_persistent.sh` 已内置)

```bash
--env HF_HOME=/hf_cache                  # HF 模型权重
--env HF_HUB_CACHE=/hf_cache/hub
--env VLLM_CACHE_ROOT=/cache/vllm        # vLLM torch.compile cache
--env TRITON_CACHE_DIR=/cache/triton     # Triton JIT
--env TORCHINDUCTOR_CACHE_DIR=/cache/torch_inductor
--env XDG_CACHE_HOME=/cache/xdg
--env TMPDIR=/cache/tmp
```

加上 bind mount:
```bash
-B $PROJECT/hf_cache:/hf_cache
-B $PROJECT/vllm_runtime_cache:/cache
```

---

## 关键参数解释(给非运维用户)

| 参数 | 通俗含义 |
|------|---------|
| `#SBATCH -t 04:00:00` | 服务器开 4 小时,到点自动关 |
| `--gres=gpu:h100-80:1` | 要 1 张 H100 80GB 显卡 |
| `--max-model-len 8192` | 单次对话最多 8192 token(prompt + 回答之和) |
| `--gpu-memory-utilization 0.92` | 显存用 92%(60GB 模型 + 14GB KV cache) |
| `--served-model-name glm47flash` | API 里模型名叫 "glm47flash" |

---

## SU 消耗参考

| 阶段 | 墙钟 | SU(h100 = 2 SU/h) |
|------|------|-------------------|
| 首次 pull + 部署验证 | ~30 min | ~1 SU |
| **日常启动**(SIF 已存) | ~5 min | ~0.2 SU |
| 4h 长驻 server | 4 h | **8 SU** |

`cis260113p` GPU 配额 1000 SU,可支持 125 次 4h server 会话。

---

## 防御机制

- Hook: `~/.claude/hooks/psc_cache_guard.py` — 拦截 inline `apptainer exec / vllm serve` 缺 cache env vars 的命令(Claude Code 全局生效)
- 触发条件: `apptainer exec` / `apptainer pull` / `vllm serve` / `vllm.entrypoints.openai` + PSC 标记(`bridges2`, `/ocean/projects/`, `cis*p`)
- `sbatch xxx.sh` **不会触发**(提交器本身不写 cache)

---

## 脚本对比

| 脚本 | 用途 | 行为 |
|------|------|------|
| `deploy_verify.sh` (v4) | **一次性验证**部署链路 | 启动 → 加载 → smoke test → **自动关机** |
| `serve_persistent.sh` (v5) | **长驻 server** 供推理/eval 调用 | 启动 → 一直跑到 walltime 或 scancel |

平时用 `serve_persistent.sh`;改环境后要验证则用 `deploy_verify.sh`。

---

## 相关链接

- 模型卡: <https://huggingface.co/zai-org/GLM-4.7-Flash>
- vLLM Docker tags: <https://hub.docker.com/r/vllm/vllm-openai/tags>
- PSC Bridges2 用户手册: <https://www.psc.edu/resources/bridges-2/user-guide/>
