# 会话摘要 — BDI 分轮 Batch Dynamic Replanning

## Session Intent

为 PNSV 项目实现**分轮 Batch Dynamic Replanning**：将串行逐实例处理（5 小时/100 实例）改为 DashScope Batch API 并行推理（几分钟/轮），费用降低 50%。同时修复生产代码中的关键 Bug。

## Key Decisions

| # | 决策 | 理由 |
|---|------|------|
| 1 | 采用"分轮 Batch"而非实时串行 | Batch API 半价 + 并行推理 + 不触发速率限制 |
| 2 | 模型选 `qwen3.5-plus` | 确认在 DashScope Batch 支持列表中 |
| 3 | 新增独立模块而非修改原脚本 | `batch_engine.py` + `run_batch_replanning.py` 与原有 `run_dynamic_replanning.py` 并存 |
| 4 | Codex 审查后全面修复 | 6 个 Bug（2×P0 + 1×P1 + 2×P2 + 1×P3）一次性全修 |
| 5 | P0 executor 修复采用 `check_goal` 参数 | 最小侵入性修改，保持 `verify_plan` 向后兼容 |

## Files Modified

### 新建文件
| 文件 | 说明 |
|------|------|
| `src/bdi_llm/batch_engine.py` | DashScope Batch API 封装（JSONL/上传/轮询/解析 + prompt 构建器） |
| `scripts/run_batch_replanning.py` | 分轮 Batch 评估脚本（Round 0 初始生成 → Round 1-3 修复） |

### 修改文件
| 文件 | 变更 |
|------|------|
| `src/bdi_llm/symbolic_verifier.py` | **[P0]** `verify_plan()` 新增 `check_goal` 参数 |
| `src/bdi_llm/dynamic_replanner/executor.py` | **[P0]** 重写：中间步骤 `check_goal=False`，最后步骤 `check_goal=True` |
| `src/bdi_llm/dynamic_replanner/replanner.py` | **[P0]** edge 归一化修复 + **[P2]** 硬编码→Config 统一配置 |
| `src/bdi_llm/dynamic_replanner/belief_base.py` | **[P3]** `query()` 支持零参数谓词 |
| `scripts/run_dynamic_replanning.py` | **[P1]** resume 去重键统一 + **[P2]** 除零 guard + 去除硬编码 |
| `src/bdi_llm/config.py` | `_resolve_key` 函数修复（先前会话）|
| `.env` | API Key 注入修复（先前会话）|

## Current State

- ✅ **6/6 Codex Bug 修复完成**，38/38 回归测试全绿
- ✅ **Batch dry-run 通过**（3 实例正确加载解析）
- 🔄 **Batch smoke test 进行中**：`batch_96defba9` 在 DashScope 异步处理 5 个 Logistics 实例（已提交约 10 分钟，状态 `in_progress`）
- ⏳ 全量实验待执行（Logistics + Depots）

## Entities & Facts

| 实体 | 信息 |
|------|------|
| API Key | `sk-0e22...390bb`（DashScope） |
| API Base URL | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 模型 | `qwen3.5-plus`（Batch + 实时均已确认支持） |
| Batch ID | `batch_96defba9-8b9c-4ebc-bf56-7af867ec4f6e` |
| File ID | `file-batch-13357f72b7044cf494ee6d9b` |
| VAL 路径 | `planbench_data/planner_tools/VAL/validate` |
| 项目路径 | `/Users/alexjiang/Desktop/BDI_LLM_Formal_Ver/` |
| Batch 费用 | 实时调用的 50% |
| JSONL 限制 | ≤50,000 请求 / ≤500 MB |

## Open Questions

1. Batch `batch_96defba9` 处理完成后的结果（初始计划生成成功率）
2. P0 executor 修复后的评估结果是否显著好于修复前
3. `qwen3.5-plus` 的 thinking mode 在 Batch 中是否正常工作
4. 全量实验（Logistics 全量 + Depots）的预计时间和成本

## Next Steps

1. **等待 Batch 完成** → 检查 5 实例 smoke test 结果
2. 如果 smoke test OK → **提交 Logistics 全量 Batch**
3. 执行 **Depots 全量 Batch**
4. 汇总四种模式（NAIVE / BDI_ONLY / FULL_VERIFIED / FULL_VERIFIED+REPAIR）对比
5. 更新 `BENCHMARKS.md`
