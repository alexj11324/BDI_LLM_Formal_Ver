# 可注入上下文 — BDI_LLM_Formal_Ver

> 为下次对话（特别是 /organize-repo）预备的精炼上下文包

---

## 项目状态（HEAD）

**PNSV** — BDI + 3 层验证 + 自动修复的 LLM 计划生成框架。
- 路径: `/Users/alexjiang/Desktop/BDI_LLM_Formal_Ver/`
- 模型: `qwen3.5-plus` via DashScope (`DASHSCOPE_API_KEY`)
- 测试: 38/38 pytest 绿色

## 本会话完成的工作

1. **新增分轮 Batch 引擎**: `src/bdi_llm/batch_engine.py` + `scripts/run_batch_replanning.py`
2. **修复 6 个生产 Bug**（Codex 审查发现）:
   - P0: `verify_plan` 增加 `check_goal` 参数解决前缀验证误判
   - P0: edge 字段归一化方向修正
   - P1: resume 去重键统一
   - P2: 除零 guard + 硬编码→Config
   - P3: BeliefBase.query() 零参数谓词

## 活跃异步任务

- **Batch `batch_96defba9`**: DashScope 处理 5 个 Logistics 实例（后台命令 `9b9fdd5d`）
  - 状态: `in_progress`（已提交 ~15 分钟）
  - 完成后输出到 `runs/batch_replanning/`

## 关键目录结构（/organize-repo 前须知）

```
BDI_LLM_Formal_Ver/
├── src/bdi_llm/           # 核心引擎
│   ├── batch_engine.py    # [NEW] Batch API 封装
│   ├── config.py          # 统一配置
│   ├── planner.py         # DSPy planner
│   ├── schemas.py         # Pydantic 模型
│   ├── symbolic_verifier.py  # VAL 验证 [MODIFIED]
│   ├── verifier.py        # 结构验证
│   ├── plan_repair.py     # DAG 修复
│   └── dynamic_replanner/
│       ├── executor.py    # [REWRITTEN] 逐步执行
│       ├── replanner.py   # [MODIFIED] LLM 重规划
│       └── belief_base.py # [MODIFIED] 状态追踪
├── scripts/
│   ├── run_batch_replanning.py   # [NEW] 分轮 Batch 评估
│   ├── run_dynamic_replanning.py # [MODIFIED] 串行评估
│   ├── run_planbench_full.py     # 全量评估（共享工具函数）
│   └── run_verification_only.py  # 验证基线
├── tests/                 # 38 tests (all green)
├── planbench_data/        # PlanBench 数据 + VAL 二进制
├── runs/                  # 实验输出
└── .env                   # API Key 配置
```

## /organize-repo 安全约束

> [!CAUTION]
> 以下文件有**活跃的外部依赖或交叉引用**，移动时需特别注意：

| 文件 | 约束 |
|------|------|
| `scripts/evaluation/run_planbench_full.py` | 被 `run_dynamic_replanning.py` 和 `run_batch_replanning.py` import（`bdi_to_pddl_actions` 等工具函数）|
| `src/bdi_llm/config.py` | 被所有模块引用 |
| `planbench_data/` | 硬编码路径在多个脚本中 |
| `.env` | `python-dotenv` 从项目根加载 |
| `tests/` | pytest.ini 配置了路径 |

## 待办（优先级排序）

1. 检查 Batch smoke test 结果
2. 全量 Logistics + Depots 实验
3. 四模式对比分析 → BENCHMARKS.md
