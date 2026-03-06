# 可注入上下文 — Session 2

> 用于下次对话的 system prompt 注入。包含当前进度、关键决策和待办事项。

---

## 项目状态快照

**PNSV (BDI + LLM Formal Verification) — Few-Shot 实施中**

### 已完成
- `bdi_engine.py` 添加 `few_shot=True/False` 参数，默认 zero-shot
- 新增 `_load_generation_demos(filename)` 通用加载方法
- 新增 `_build_blocksworld_demos()`, `_build_depots_demos()`, `_build_repair_demos()`
- 创建 `data/blocksworld_demos.yaml` (2 demos), `data/depots_demos.yaml` (2 demos), `data/repair_demos.yaml` (2 demos)
- 已有 `data/logistics_demos.yaml` (2 demos) — 现在也受 `few_shot` 参数控制

### 未完成（下次优先）
1. **验证 YAML + demo 加载** — 脚本被取消，需重新运行
2. **`run_planbench_full.py` 添加 `--few_shot` flag** — 传递给 `BDIPlanner(few_shot=True)`
3. **重命名 execution_mode** — NAIVE→BASELINE, FULL_VERIFIED→ZERO_SHOT/FEW_SHOT
4. **Smoke test** — `--few_shot` vs 不加，对比 logistics 3 题的修复成功率

### 命名规范（已定）
| 模式 | 含义 |
|------|------|
| `BASELINE` | LLM 直出 PDDL，无 BDI |
| `ZERO_SHOT` | BDI + 验证 + 修复，无 demo |
| `FEW_SHOT` | BDI + 验证 + 修复 + demo |

### 关键文件
- Engine: `src/bdi_llm/planner/bdi_engine.py`
- Signatures: `src/bdi_llm/planner/signatures.py`
- Demos: `src/bdi_llm/data/*.yaml`
- Benchmark: `scripts/evaluation/run_planbench_full.py`

### 用户偏好
- 命名要学术规范，不要 NAIVE、不要冗余前缀
- 重心放在 prompt engineering 而非代码修修补补
- 保留 zero-shot 对照组用于消融实验
