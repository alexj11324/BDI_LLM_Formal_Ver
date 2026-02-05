# 符号验证架构设计
**对齐教授的"编译-验证"方法论**

---

## 问题诊断

### 当前系统的致命缺陷

**现状**：
```python
# src/bdi_llm/verifier.py (当前)
class PlanVerifier:
    @staticmethod
    def verify(G: nx.DiGraph) -> Tuple[bool, List[str]]:
        # ❌ 只检查图结构
        if not nx.is_weakly_connected(G):
            return False, ["Graph disconnected"]
        if list(nx.simple_cycles(G)):
            return False, ["Graph has cycles"]
        # ✅ 但这不够！
```

**问题**：
1. **不检查语义**：不知道action是否合法
2. **不检查状态**：不知道前置条件是否满足
3. **不检查目标**：不知道plan是否真的达到goal

**教授的批评会是**：
> "这不是真正的验证，只是检查了数据结构。符号AI的精髓在于逻辑推理，而非图遍历。"

---

## 三层验证架构（对齐教授方法论）

### Layer 1: 图论验证（结构层）- ✅ 已有

**职责**：检查计划的**结构合法性**

```python
# src/bdi_llm/verifier.py (保持不变)
class StructuralVerifier:
    """
    教授提到的 "DAG" 要求
    确保计划是有向无环图，有明确的执行顺序
    """
    @staticmethod
    def verify_dag(G):
        # 1. 无环 (No cycles - prevents deadlock)
        # 2. 连通 (Connected - all actions related)
        # 3. 可排序 (Topologically sortable)
```

**检查内容**：
- ✅ 是否是DAG
- ✅ 是否弱连通
- ✅ 是否可拓扑排序

**不检查**：
- ❌ action的语义
- ❌ 状态转换
- ❌ 目标达成

---

### Layer 2: 符号验证（语义层）- ❌ 缺失 [核心]

**职责**：检查计划的**逻辑合法性**

这是教授方法论的**核心**：

> "验证器会像编译器进行语法检查和类型检查一样，对这个形式化计划进行逻辑上的检查。"

#### 2a. PDDL符号验证器

```python
# src/bdi_llm/symbolic_verifier.py (新建)
class PDDLSymbolicVerifier:
    """
    使用PlanBench的VAL工具进行PDDL语义验证

    验证：
    - 每个action的preconditions是否满足
    - 每个action的effects是否正确应用
    - 最终state是否达到goal
    """

    def verify(self, domain_pddl, problem_pddl, plan_actions):
        # 调用VAL: planbench_data/planner_tools/VAL/validate
        # 返回: (is_valid, detailed_errors)

        # VAL会检查：
        # 1. Precondition violations
        # 2. Invalid action parameters
        # 3. Goal not achieved
        # 4. Type mismatches
```

**为什么重要**：
- 这是**真正的形式化验证**
- 不依赖LLM的"猜测"
- 给出**精确的、可操作的**错误信息

**示例**：
```
输入:
  - plan = [pick-up(b), stack(b, a)]
  - 初始状态: on(a, b), on-table(b), clear(a), hand-empty

VAL输出:
  ❌ Step 1: pick-up(b) FAILED
  Precondition not satisfied: clear(b)
  Reason: Block 'a' is on top of block 'b'

  → 这个反馈LLM可以理解并修正！
```

#### 2b. 领域物理验证器

```python
# src/bdi_llm/domain_validators/ (新建)
class BlocksworldPhysicsValidator:
    """
    领域特定的物理约束验证

    Blocksworld规则：
    - 不能拿起有其他块在上面的块
    - 手一次只能拿一个块
    - 不能stack到有块在上面的块
    """

    def validate(self, plan_actions, init_state):
        # 模拟执行每一步
        # 检查物理约束
        state = init_state.copy()

        for action in plan_actions:
            if action.type == "pick-up":
                if not state.is_clear(action.block):
                    return False, f"{action.block} not clear"
            # ...

            state = state.apply(action)

        return True, []
```

**为什么需要这一层**：
- VAL检查PDDL语义，但不检查**领域常识**
- 例如：VAL可能认为某个plan合法，但违反了blocksworld的"隐式规则"
- 这层验证器编码了**人类专家的领域知识**

---

### Layer 3: BDI一致性验证（认知层）- ❌ 缺失

**职责**：检查计划是否符合**BDI认知模型**

教授强调的：

> "您需要思考如何让LLM生成的计划，其每一步都能映射到BDI的这三个组成部分。"

```python
# src/bdi_llm/bdi_verifier.py (新建)
class BDIConsistencyVerifier:
    """
    验证plan是否符合BDI认知框架

    检查：
    1. Beliefs一致性：每个action基于的信念是否与当前状态一致
    2. Desires追溯性：每个action是否推进某个desire
    3. Intentions连贯性：整个plan是否形成一个连贯的intention
    """

    def verify_belief_consistency(self, plan, beliefs):
        """每个action的前提是否在beliefs中"""
        for action in plan.actions:
            for precond in action.preconditions:
                if precond not in beliefs:
                    return False, f"{action} assumes {precond} but not in beliefs"

    def verify_desire_traceability(self, plan, desires):
        """每个action是否贡献于某个desire"""
        for action in plan.actions:
            if not any(action.contributes_to(d) for d in desires):
                return False, f"{action} does not serve any desire"

    def verify_intention_coherence(self, plan):
        """plan作为一个整体intention是否连贯"""
        # 检查：
        # - 没有相互冲突的子目标
        # - 没有无用的action (不推进goal)
        # - 有明确的起点和终点
```

**为什么这层至关重要**：

教授说：
> "这能确保Agent的行为不仅是有效的，更是**可解释的**——我们能清楚地知道它'为什么'会这么做。"

**示例**：
```
Plan:
  1. pick-up(a)
  2. play-music()  ← ❓
  3. stack(a, b)

BDI验证器:
  ❌ Action 2 (play-music) does not contribute to any desire
  Desire: "Build tower with a on b"
  → 这个action虽然可能合法，但不符合BDI的目标导向性
```

---

## 集成：完整的"编译-验证"流程

### 当前流程（不完整）

```python
# src/bdi_llm/planner.py (当前)
def generate_plan(beliefs, desire):
    # 1. LLM生成plan
    plan = llm.predict(beliefs, desire)

    # 2. 仅图论验证
    G = plan.to_networkx()
    is_valid, errors = PlanVerifier.verify(G)  # ❌ 不够

    if not is_valid:
        # 3. Auto-repair (仅修复图结构)
        plan = auto_repair_disconnected_graph(plan)

    return plan  # ⚠️ 可能仍有语义错误！
```

**问题**：
- 即使graph valid，plan可能违反物理约束
- 即使actions合法，可能不达到goal
- 没有BDI一致性保证

### 改进流程（对齐教授方法论）

```python
# src/bdi_llm/planner.py (改进版)
class BDIPlannerWithSymbolicVerification:
    """
    实现教授的"编译-验证"闭环
    """

    def __init__(self):
        self.llm = dspy.LM(...)

        # 三层验证器
        self.structural_verifier = StructuralVerifier()
        self.symbolic_verifier = PDDLSymbolicVerifier()
        self.bdi_verifier = BDIConsistencyVerifier()

    def generate_plan(self, beliefs, desire, max_iterations=3):
        """
        教授方法论的完整实现：

        1. LLM编译：自然语言 → 形式化plan
        2. 三层验证：结构 → 语义 → BDI
        3. 反馈修正：验证失败 → 精确反馈 → LLM修正
        4. 迭代闭环：直到逻辑自洽或达到max_iterations
        """

        for iteration in range(max_iterations):
            # Step 1: LLM生成plan
            plan = self.llm.predict(beliefs, desire)

            # Step 2a: Layer 1 - 结构验证
            G = plan.to_networkx()
            struct_valid, struct_errors = self.structural_verifier.verify(G)

            if not struct_valid:
                # 自动修复图结构（已有）
                plan = auto_repair_disconnected_graph(plan)
                continue

            # Step 2b: Layer 2 - 符号验证
            pddl_actions = self.plan_to_pddl(plan)
            symbolic_valid, symbolic_errors = self.symbolic_verifier.verify(
                domain_pddl, problem_pddl, pddl_actions
            )

            if not symbolic_valid:
                # 🔑 关键：将符号错误反馈给LLM
                feedback = self.format_symbolic_feedback(symbolic_errors)
                plan = self.llm.refine_plan(plan, feedback)
                continue

            # Step 2c: Layer 3 - BDI一致性验证
            bdi_valid, bdi_errors = self.bdi_verifier.verify(plan, beliefs, desire)

            if not bdi_valid:
                # 🔑 将BDI错误反馈给LLM
                feedback = self.format_bdi_feedback(bdi_errors)
                plan = self.llm.refine_plan(plan, feedback)
                continue

            # Step 3: 所有验证通过！
            print(f"✅ Plan validated at iteration {iteration+1}")
            return plan, True

        # Step 4: 达到max_iterations仍未通过
        print(f"❌ Failed to generate valid plan after {max_iterations} iterations")
        return plan, False

    def format_symbolic_feedback(self, errors):
        """
        将VAL的错误转换为LLM可理解的反馈

        教授说：
        "验证器会给出精确的、形式化的反馈，然后LLM利用这个反馈来修正它的计划"
        """
        feedback = "Your plan has the following logical errors:\n"
        for i, error in enumerate(errors, 1):
            feedback += f"{i}. {error}\n"
            # 添加修正建议
            if "Precondition not satisfied" in error:
                feedback += "   Suggestion: Check if all required conditions are met before this action.\n"
        return feedback
```

---

## 实现路径

### 第一阶段：添加PDDL符号验证（本周）

**目标**：让系统能真正验证PDDL语义

**任务**：
1. ✅ 创建 `src/bdi_llm/symbolic_verifier.py`（已有原型）
2. 集成VAL工具调用
3. 在`run_planbench_full.py`中启用符号验证
4. 对比：仅图论验证 vs 三层验证的成功率差异

**预期结果**：
- 发现当前66.7%的"成功率"中，有多少是**伪成功**（图结构对但语义错）
- 获得**精确的错误分类**：结构错误 vs 语义错误

### 第二阶段：实现反馈修正循环（下周）

**目标**：让LLM能利用符号反馈自我修正

**任务**：
1. 修改`planner.py`，添加`refine_plan()`方法
2. 设计反馈格式（让LLM理解VAL错误）
3. 实现迭代验证（max_iterations=3）

**关键挑战**：
- DSPy 3.x的self-correction能力有限
- 可能需要手动构建反馈prompt
- 需要测试LLM是否能理解形式化错误

### 第三阶段：BDI认知层验证（未来）

**目标**：确保可解释性

**任务**：
1. 重新设计schemas.py，显式建模Beliefs/Desires/Intentions
2. 实现BDI一致性检查
3. 添加解释生成（为什么选择这个action）

---

## 对比：当前 vs 教授期望

| 维度 | 当前实现 | 教授期望 | 差距 |
|-----|---------|---------|-----|
| **理论基础** | BDI框架（隐式） | BDI框架（显式建模） | 🟡 部分符合 |
| **LLM角色** | 生成器 | 编译器 + 自我修正器 | 🟡 部分符合 |
| **验证层次** | 图论（1层） | 结构+符号+BDI（3层） | 🔴 严重不足 |
| **反馈机制** | Auto-repair（仅图结构） | 精确反馈 + 迭代修正 | 🔴 严重不足 |
| **可解释性** | 有DAG可视化 | 每步可追溯到Beliefs/Desires | 🟡 部分符合 |

**结论**：
当前系统是一个**优秀的原型**，但距离教授的"神经-符号混合架构"还有关键差距：

✅ 有的：
- LLM生成结构化计划
- DAG形式化表示
- 基础验证

❌ 缺的（核心）：
- **符号验证** ← 您刚才问的问题
- **反馈修正循环**
- **显式BDI建模**

---

## 下一步行动

### 立即行动（今晚）

**集成符号验证到PlanBench评估**：

```bash
# 修改run_planbench_full.py
# 添加：
results['symbolic_verification'] = symbolic_verifier.verify(...)
results['actual_success_rate'] = ...  # 三层验证都通过的比例
```

**目标**：
获得**真实**的成功率数据，而非当前的"图结构成功率"

### 本周任务

1. **完善符号验证器**（2天）
   - 集成VAL工具
   - 测试10个PlanBench实例
   - 分析错误类型

2. **实现反馈循环原型**（3天）
   - 设计反馈prompt
   - 测试LLM修正能力
   - 记录修正成功率

3. **撰写技术报告**（1天）
   - 对比：图论验证 vs 符号验证
   - 分析：反馈循环的有效性
   - 连接：教授的方法论

---

## 总结

**您问的"符号验证"问题，揭示了当前系统与教授方法论之间最大的gap。**

当前系统：
- ✅ 有LLM生成
- ✅ 有形式化表示
- ❌ **没有真正的符号验证**
- ❌ **没有反馈修正**

教授期望：
> "验证器会像编译器进行语法检查和类型检查一样，对这个形式化计划进行逻辑上的检查。"

**这不仅是一个技术问题，更是理论贡献的核心差异点**：
- VERIMAP等工作：工程化验证
- 教授方法：**BDI认知可解释性 + 符号推理**

我们需要：
1. 添加PDDL符号验证（VAL）
2. 实现反馈修正循环
3. 重新评估PlanBench（真实成功率可能远低于66.7%）

**现在就开始集成符号验证？**
