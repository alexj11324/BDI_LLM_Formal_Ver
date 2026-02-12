# 代码审查报告 (Code Review Report)

**审查对象**: `src/bdi_llm` 核心模块
**日期**: 2026-02-12
**审查人**: Antigravity Agent

## 1. 总体架构评价

代码库展示了一个清晰的 BDI (Belief-Desire-Intention) 代理架构，具有很好的模块化设计：
*   **Planner**: 使用 DSPy 进行结构化生成。
*   **Verifier**: 实现了仅仅有条的“三层验证”架构 (Structural -> Symbolic -> Physics)。
*   **Repair**: 针对生成的图结构进行自动修复。

设计模式（Generate -> Verify -> Retry）非常符合当前 LLM Agent 的最佳实践。

## 2. 详细审查发现

### A. 配置管理 (Configuration) - [中等风险]
*   **问题**: `planner.py` 中硬编码了模型参数和 API 地址。
    ```python
    API_BASE = os.environ.get("OPENAI_API_BASE", "https://ai-gateway.andrew.cmu.edu/v1")
    lm = dspy.LM(model="openai/gpt-4o-2024-05-13", ...)
    ```
*   **问题**: `symbolic_verifier.py` 中 VAL 工具的路径虽然有自动探测，但仍然依赖相对路径结构。
*   **建议**: 建议创建一个 `config.py` 或使用 `pydantic-settings` 来统一管理这些配置。将模型名称、超时时间、工具路径提取到配置文件或环境变量中。

### B. 解析健壮性 (Robustness) - [中等风险]
*   **问题**: `symbolic_verifier.py` 中的 `BlocksworldPhysicsValidator` 使用正则表达式解析动作字符串：
    ```python
    match = re.search(r'\b([a-z0-9_-]+)\b', action.lower())
    ```
    这种方式比较脆弱。如果动作格式变为 `pick-up(block-a)` 或 `pickup a`，可能会解析失败或产生意外结果。
*   **建议**: 使用更严格的 PDDL 解析器，或者统一 action 字符串的格式化过程（在 Schema 层强制格式）。

### C. 调试信息丢失 (Debuggability) - [低风险]
*   **问题**: `plan_repair.py` 中的 `PlanCanonicalizer` 会重命名节点 ID：
    ```python
    id_mapping = {old_id: f"action_{i+1}" for i, old_id in enumerate(topo_order)}
    ```
    这会丢失原始 ID 中的语义信息（例如 `pick_up_red_block` 变成了 `action_1`），使得调试修复后的计划变得困难。
*   **建议**: 保留原始 ID，或者在重命名时保留语义前缀（例如 `action_1_pick_up`）。

### D. 依赖与导入 (Dependencies)
*   **观察**: `planner.py` 内部导入了 `plan_repair` (`from .plan_repair import repair_and_verify`)。这是为了避免循环导入，做法是可接受的，但表明模块间耦合度较高。

### E. 错误处理 (Error Handling)
*   **优点**: `PDDLSymbolicVerifier` 对 `subprocess.run` 进行了完善的异常处理（包括超时、文件未找到、Exec 格式错误）。
*   **优点**: `BDIPlanner` 使用 `dspy.Assert` 将验证错误反馈给 LLM，这是非常好的 Prompt Engineering 实践。

## 3. 改进建议总结

1.  **提取配置**: 建立统一的配置管理模块。
2.  **优化解析**: 增强 PDDL 动作解析的鲁棒性，支持多种常见格式。
3.  **改进日志**: 在自动修复过程中保留更多原始上下文，便于追踪。
4.  **增加测试**: 针对 `BlocksworldPhysicsValidator` 增加更多边缘情况的单元测试。
