# 记忆更新日志 — Session 2

**会话 ID**: `ab39b49d-5884-408e-941a-3abf2612e87e`  
**时间**: 2026-03-05T15:14 EST

---

## 短期记忆（当前会话操作细节）

| 时间 | 事件 | 状态 |
|------|------|------|
| 14:00 | Checkpoint 恢复，继续 few-shot 实施 | ✅ |
| 14:10 | Bug 修复回顾：path bug (.parent×3)、serialization bug (list vs dict) | ✅ 已修 |
| 14:20 | 论文阅读：FormalJudge + STILL-ALIVE | ✅ 归档为 paper_comparison.md |
| 14:35 | Few-shot 实施计划编写、用户批准 | ✅ |
| 14:45 | 用户要求保留 zero-shot + 命名调整 | ✅ 方案变更 |
| 14:50 | 创建 3 个 YAML 文件 + 修改 bdi_engine.py | ✅ |
| 14:52 | 验证脚本执行 — hang/取消 | ❌ 未完成 |
| 15:14 | 用户触发 /chat-summarize | 当前 |

## 长期记忆（已验证的决策/模式）

### 架构决策
- **Few-shot 通过 `BDIPlanner(few_shot=True/False)` 控制** — 默认 False 保持 zero-shot
- **Demo 加载统一用 `_load_generation_demos(filename)` 方法** — 3 domain 共用
- **Repair demo 是 domain-agnostic 的** — 通用错误模式，不需要 per-domain

### 命名规范
- `BASELINE` = 直接 LLM 出 PDDL，无 BDI 分解
- `ZERO_SHOT` = BDI 分解 + 验证 + 修复，无 demo
- `FEW_SHOT` = BDI 分解 + 验证 + 修复 + few-shot demo

### 技术模式
- DSPy 的 few-shot 注入方式：`module.demos = [dspy.Example(...).with_inputs(...)]`
- YAML 文件路径解析：`Path(__file__).parent.parent / "data" / filename`

## 实体记忆

| 实体 | 类型 | 更新内容 |
|------|------|----------|
| `BDIPlanner` | 类 | 新增 `few_shot` 参数，新增 4 个 demo 构建方法 |
| `RepairPlan` | Signature | 现在支持 few-shot demo 注入（via `self.repair_plan.demos`） |
| `data/` | 目录 | 新增 3 个 YAML 文件（blocksworld_demos, depots_demos, repair_demos） |
| 用户偏好 | 偏好 | 不喜欢 NAIVE 命名；不喜欢冗余前缀（BDI_）；追求学术规范命名 |
