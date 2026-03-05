# Compressed Session Summary — BDI Dynamic Replanning
> Generated: 2026-03-05 | Layer: context-compression (算法层)
> Method: Anchored Iterative Summarization
> Compression: ~45,000 tokens conversation → ~800 words structured summary

## Session Intent

实现 BDI-LLM (PNSV) 项目的 Dynamic Replanning 子系统，使评测流水线具备"运行时检测执行偏差 → 触发 LLM 重新规划"的能力，并跑通端到端测试。

## Root Cause of Current Blocker

`DASHSCOPE_API_KEY` 未注入运行环境。`.env` 使用了 `${DASHSCOPE_API_KEY}` 语法，但 `python-dotenv` 不执行 Shell 变量展开，导致 `litellm` 收到空 API key，抛出 `BadRequestError`。

## Files Modified

| File | Action | What Changed & Why |
|------|--------|--------------------|
| `src/bdi_llm/dynamic_replanner/belief_base.py` | **NEW** | 从 PDDL `:init` 解析命题集合，支持 `apply_effects()` (STRIPS add/delete)，`to_natural_language()` 序列化供 LLM prompt 使用 |
| `src/bdi_llm/dynamic_replanner/__init__.py` | MODIFIED | 导出 `BeliefBase` |
| `scripts/run_dynamic_replanning.py` | MODIFIED | 增加 `--resume` 检查点续跑逻辑，采用原子写入 (`tmp → os.rename()`) |
| `src/bdi_llm/planner.py` | MODIFIED | 统一超时为 `Config.TIMEOUT` (600s)，替代硬编码 120s |
| `src/bdi_llm/dynamic_replanner/executor.py` | MODIFIED | 对齐超时至 `Config.TIMEOUT` |
| `.env` | MODIFIED | 模型切换至 `qwen3.5-plus`；`LLM_TIMEOUT=600` |

## Decisions Made

1. **超时统一策略**：所有 LLM 调用统一使用 `Config.TIMEOUT` (600s)，不做逐调用精调。理由：`qwq-plus` 深度推理时间不可预测，宽松上限避免评测中的误杀。
2. **PDDL 解析轻量化**：`BeliefBase` 用正则而非完整 PDDL 语法解析器。够用于 Blocksworld/Logistics/Depots，复杂域需升级。
3. **检查点原子性**：`write-to-temp → os.rename()` 保证 POSIX 原子性，防止中断产出损坏 JSON。
4. **分支隔离**：Auto-repair 严格限制在 `feature/repair` 分支，`main` 分支仅做 Verification Only。

## Current State

- ✅ `BeliefBase` 单元测试通过（blocksworld 4 objects, 8 propositions）
- ✅ 全部 import 成功
- ✅ 脚本正常启动、600s 超时生效、逻辑未挂起
- ❌ E2E 测试在 Init 阶段失败：`Init=✗ | Replans=0 | Final=✗`
- ❌ 原因：`DASHSCOPE_API_KEY` 缺失

## Next Steps

1. 注入 `DASHSCOPE_API_KEY`（硬编码进 `.env` 或 `export` 到 Shell）
2. 重跑 `python scripts/run_dynamic_replanning.py --domain blocksworld --instances 1`
3. 验证初始规划生成 → 执行模拟 → 偏差检测 → 重规划触发的全链路
4. 扩展到 Logistics / Depots 域
