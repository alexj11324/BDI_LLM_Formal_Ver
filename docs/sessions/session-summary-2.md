# 结构化会话摘要 — Session 2

**会话 ID**: `ab39b49d-5884-408e-941a-3abf2612e87e`  
**时间**: 2026-03-05 ~14:00–15:14 EST

---

## Session Intent

为 BDI planner 的 plan generation 和 plan repair 阶段添加 **few-shot learning 示例**，替代当前纯 prompt instructions 的 zero-shot 方案。目标是从"下游修代码"转向"上游教 LLM"，提升泛化能力。

## Key Decisions

| 决策 | 理由 |
|------|------|
| **命名规范统一为 BASELINE / ZERO_SHOT / FEW_SHOT** | 用户明确要求：不用 NAIVE（不好听）、不加 BDI_ 前缀（标题已说明） |
| **保留 zero-shot 作为对照** | `BDIPlanner(few_shot=False)` 保持原有行为，`few_shot=True` 启用 demo 注入，便于消融实验 |
| **Repair few-shot 使用 logistics 场景但 domain-agnostic** | repair 错误模式（unsatisfied precondition / goal not satisfied）是通用的，不需要每个 domain 单独写 |
| **重构 `_build_logistics_demos()` 为通用 `_load_generation_demos(filename)`** | 消除代码重复，3 个 domain 共用同一套加载逻辑 |
| **策略转向：从 if/else parsing hack → few-shot prompt engineering** | 用户和教授均认为在代码层面修修补补是 overfitting，不具备学术贡献 |

## Files Modified

| 文件 | 变更类型 | 摘要 |
|------|----------|------|
| `src/bdi_llm/planner/bdi_engine.py` | MODIFY | 添加 `few_shot` 参数；抽取 `_load_generation_demos()`；新增 `_build_blocksworld_demos()`、`_build_depots_demos()`、`_build_repair_demos()`；将 logistics demo 从 always-on 改为 few_shot 条件注入 |
| `src/bdi_llm/data/blocksworld_demos.yaml` | NEW | 2 个 blocksworld generation 示例（2-block 重排 + 3-block 塔堆叠） |
| `src/bdi_llm/data/depots_demos.yaml` | NEW | 2 个 depots generation 示例（单 depot 运输 + 双 depot 多 crate） |
| `src/bdi_llm/data/repair_demos.yaml` | NEW | 2 个 repair 示例（unsatisfied precondition 修复 + goal not satisfied 修复） |
| `scripts/evaluation/run_planbench_full.py:146` | MODIFY | （会话早期）修复 domain 文件路径 `.parent.parent` → `.parent.parent.parent` |
| `scripts/evaluation/run_planbench_full.py:1404-1418` | MODIFY | （会话早期）修复 `plan_nodes` 序列化 bug，兼容 list/dict 类型 |

## Current State

- ✅ 3 个 YAML demo 文件已创建
- ✅ `bdi_engine.py` 已修改，支持 `few_shot=True/False`
- ❌ **验证未完成** — YAML 结构验证和 demo 加载测试被取消/挂起
- ❌ **benchmark 脚本未改** — `run_planbench_full.py` 还未添加 `--few_shot` flag
- ❌ **execution_mode 重命名未做** — 还是 NAIVE/FULL_VERIFIED

## Entities & Facts

| 实体 | 类型 | 信息 |
|------|------|------|
| `data/logistics_demos.yaml` | 文件 | 已存在，2 个 logistics generation demo |
| `data/blocksworld_demos.yaml` | 文件 | 新建，2 个 blocksworld generation demo |
| `data/depots_demos.yaml` | 文件 | 新建，2 个 depots generation demo |
| `data/repair_demos.yaml` | 文件 | 新建，2 个 domain-agnostic repair demo |
| `RepairPlan` | DSPy Signature | 在 `signatures.py`，含 VAL 错误解读指南，现在通过 `_build_repair_demos()` 可注入 few-shot |
| FormalJudge (2510.03469) | 论文 | Dafny spec 驱动的 LLM 修复循环——原子事实分解策略可借鉴 |
| STILL-ALIVE (2602.11136) | 论文 | NL spec → Dafny spec → LLM 修代码——specification language 对修复效果影响大 |

## Open Questions

1. **benchmark 脚本的 `--few_shot` flag 如何传递？** — 需要在 `run_planbench_full.py` 的 `BDIPlanner` 实例化处添加参数
2. **execution_mode 枚举值重命名是否需要全局 grep？** — 可能有其他脚本/文档引用 NAIVE / FULL_VERIFIED
3. **repair demo 数量是否足够？** — 当前只有 2 个（unsatisfied precondition + goal not satisfied），可能需要添加更多错误类型（如 duplicate action、wrong parameter order）
4. **验证命令为什么会 hang？** — 可能是 pydantic/networkx 的 import 在某些环境下慢

## Next Steps

1. **跑验证** — YAML 结构验证 + demo 加载测试
2. **修改 `run_planbench_full.py`** — 添加 `--few_shot` 参数，传递给 `BDIPlanner`
3. **重命名 execution_mode** — NAIVE→BASELINE, FULL_VERIFIED→ZERO_SHOT/FEW_SHOT
4. **Smoke test** — 用 logistics 3 题验证 few_shot=True vs False 的效果差异
