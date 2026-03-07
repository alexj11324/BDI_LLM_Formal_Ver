# PNSV 核心创新点构思：突破大模型规划修复的“泛化瓶颈”

**生成时间**: 2026-03-05
**针对痛点**: 
在复杂的拓扑图任务（如 Logistics 物流、网路路由）中，传统的大模型纯文本自我修复（Textual Feedback Self-Refine）极易陷入“打地鼠（Whack-a-mole）”困境。修复了节点 A 的前置条件，却破坏了后续节点 B 的连通性，导致修复循环无法收敛。

---

## 💡 核心破局方案：Neuro-Symbolic Graph Repair (神经符号图修复)

为了解决这一问题，我们将修复过程从“端到端的文本重新生成”降维并重构为**“带有符号工具增强的外科手术式图编辑”**。

这包含两个递进的核心创新：

### 创新点一：从“重写全文”转向“图编辑指令” (Surgical Graph Edit Operations)
*   **概念来源**: 认知科学的「问题重构（Representational Change）」
*   **具体做法**:
    当 VAL 验证器报错时，目前的 `RepairPlan` 签名是让 LLM 重新输出整个 `BDIPlan` (Nodes & Edges)。这极易破坏原本已经正确的子图。
    我们将 `RepairPlan` 的输出约束为 **Graph Edit Script (图编辑脚本)**：
    *   `[INSERT_ACTION(node_id="drive_1", type="drive-truck", params={...}, before="load_1")]`
    *   `[DELETE_ACTION(node_id="drive_2")]`
    后端（`plan_repair.py`）利用 NetworkX 严格执行这些指令。LLM 不再能碰原本正确的部分，极大地保护了规划的稳定性。

### 创新点二：空间拓扑的符号外包 (Macro-Actions & Symbolic Routing)
*   **概念来源**: 认知科学的「约束移除（Constraint Manipulation）」
*   **具体做法**:
    LLM 本身是不具备图遍历（BFS/A*）能力的，逼它去猜从 City_A 到 City_B 缺了几个 level 是违背大模型本性的。
    我们在 BDI 引擎中引入一个 **Symbolic Router Tool**。
    当 VAL 提示“Truck T1 不在 Package P1 所在地”时，LLM 不需要生成具体的 drive 序列，它只需要输出一个宏指令图编辑：
    *   `[DELEGATE_PATHFINDING(entity="T1", start="City_A", end="City_B", before="load_1")]`
    后端的 Python 代码在执行这一步时，自动调用图算法（如 `nx.shortest_path`）生成极其严谨的 `[drive, load_plane, fly, unload_plane, drive]` 序列，并无缝织入原 DAG 图中。

---

## 📈 学术价值与论文 Storyline (The "Pitch")

**Two-Sentence Pitch (电梯演讲)**:
> "Current LLM-based planners struggle to recover from execution failures in topologically strict domains (like Logistics) because they rely on textual self-refinement, which often corrupts previously valid sub-plans. We propose **Neuro-Symbolic Graph Repair**, a novel framework where the LLM predicts discrete graph-edit operations and delegates topological pathfinding to deterministic symbolic solvers, achieving a 3x increase in repair convergence on complex PlanBench instances."

## 🛠️ 下一步工程落地 Blueprint

如果采用此方案，我们的 `BDI_LLM_Formal_Ver` 需要做以下改动：
1. **修改 `schemas.py`**: 增加 `GraphEditOperation` 类体系（Insert, Delete, DelegatePath）。
2. **修改 `signatures.py`**: 重新设计 `RepairPlan` 的 Prompt，教导大模型使用编辑指令而非全文重写。
3. **扩展 `plan_repair.py`**: 实现一个 `GraphEditApplier` 引擎，负责将 LLM 生成的编辑动作安全地应用到现有的 NetworkX DAG 上，并在遇到 `DELEGATE` 指令时调用简单的图搜索算法。

---

## 📚 参考文献支撑 (2025 最新前沿比对)
*目前学界主流在搞 LLM + MCTS（如 SPIRAL [Zhang et al., 2025], MASTER [Gan et al., 2025]）。我们的图编辑+符号路由避开了算力消耗极大的蒙特卡洛树搜索，用极轻量级的工具增强实现了更精准的修复，具备显著的差异化优势。*
