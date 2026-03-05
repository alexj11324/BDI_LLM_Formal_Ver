# 记忆更新日志

> 来源会话: `dfa280c4-9a8c-43ed-9007-764a7cd99f82`
> 时间戳: 2026-03-05T05:39:00-05:00

---

## 短期记忆（当前会话操作细节）

| 项 | 内容 |
|----|------|
| Batch 命令 ID | `9b9fdd5d-cb5d-4f29-8e93-c6314442707a`（后台轮询中） |
| Batch job ID | `batch_96defba9-8b9c-4ebc-bf56-7af867ec4f6e` |
| 上传文件 ID | `file-batch-13357f72b7044cf494ee6d9b` |
| 测试命令 | `python3 -m pytest tests/test_verifier.py tests/test_symbolic_verifier.py tests/test_plan_repair.py -v` |
| Dry-run 命令 | `python3 scripts/run_batch_replanning.py --domain logistics --max_instances 3 --dry_run` |
| 环境变量 | `DASHSCOPE_API_KEY=sk-0e22...390bb`, `PYTHONUNBUFFERED=1` |

## 长期记忆（已验证的架构决策）

### Batch 分轮架构
- Round 0: 提交所有实例初始计划生成 → JSONL batch
- 本地: VAL 逐步验证 → 分流 PASS/FAIL
- Round 1-N: 失败实例打包修复 → 新 batch（最多 3 轮）
- 成本节省 50%，消除速率限制

### P0 修复模式：check_goal 参数
- `verify_plan(check_goal=False)` 对前缀验证只检查 precondition，忽略 goal
- `PlanExecutor` 中间步骤用 `check_goal=False`，最后步骤用 `check_goal=True`
- 这修复了"正常中间步骤被误判失败"的根本问题

### Config 统一配置
- `DynamicReplanner` 不再硬编码 API key/base_url
- 通过 `Config.DASHSCOPE_API_KEY or Config.OPENAI_API_KEY` 支持双通道
- 模型名从 `Config.LLM_MODEL` 读取，fallback `qwen3.5-plus`

## 实体记忆

### 项目
| 属性 | 值 |
|------|-----|
| 名称 | PNSV (Pluggable Neuro-Symbolic Verification) |
| 路径 | `/Users/alexjiang/Desktop/BDI_LLM_Formal_Ver/` |
| 语言 | Python 3.13 |
| 框架 | DSPy, OpenAI SDK, Pydantic, NetworkX |
| 测试框架 | pytest (38 tests) |
| 评估域 | Blocksworld, Logistics, Depots |

### 服务
| 服务 | 端点 | 凭据 |
|------|------|------|
| DashScope | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `DASHSCOPE_API_KEY` env var |
| VAL | `planbench_data/planner_tools/VAL/validate` | 本地二进制 |

### 关键文件映射

| 文件 | 职责 |
|------|------|
| `src/bdi_llm/batch_engine.py` | Batch API 封装（新建） |
| `scripts/run_batch_replanning.py` | 分轮 Batch 评估（新建） |
| `src/bdi_llm/symbolic_verifier.py` | PDDL/VAL 验证（check_goal 已修） |
| `src/bdi_llm/dynamic_replanner/executor.py` | 逐步执行器（check_goal 已修） |
| `src/bdi_llm/dynamic_replanner/replanner.py` | LLM 重规划器（归一化+Config 已修） |
| `src/bdi_llm/dynamic_replanner/belief_base.py` | 状态追踪（query 已修） |
| `src/bdi_llm/config.py` | 统一配置 |
| `src/bdi_llm/schemas.py` | Pydantic 模型（ActionNode, DependencyEdge, BDIPlan） |
| `scripts/run_dynamic_replanning.py` | 串行评估脚本（resume+除零已修） |
| `scripts/evaluation/run_planbench_full.py` | 全量评估（提供共享工具函数） |

### 已知问题（已修复）
| ID | 问题 | 修复 |
|----|------|------|
| P0-1 | executor 前缀验证误判 | `check_goal` 参数 |
| P0-2 | edge 归一化方向错误 | `source`/`target` 正确映射 |
| P1 | resume 去重键不一致 | 异常分支添加 `instance_file` |
| P2-1 | total==0 除零 | guard 检查 |
| P2-2 | 硬编码模型/endpoint | Config 统一 |
| P3 | query() 零参数谓词 | 双条件匹配 |
