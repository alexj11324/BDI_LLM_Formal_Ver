# PNSV Framework — Phase 2 Architectural Directive (SOTA Evolution)

> **分类**: 项目核心对齐文档  
> **来源**: Deep Think Agent → Claude Opus 4.6  
> **目标**: 动态拓扑重规划（逻辑梯度注入 + 动态图外科手术）  
> **前置依赖**: Phase 1 Directive (`PNSV_PHASE1_DIRECTIVE.md`)

---

## 设计理念

原架构中的 `suspended_intentions`（任务挂起栈）和 `BaseDomainVerifier`（多态验证总线）是为"局部重规划"量身定制的锚点。Phase 2 的目标是：**绝不推翻底座，而是对核心引擎进行"微观手术"**，将原本"一旦报错全盘重绘"的笨重逻辑，升级为具备**"局部自愈能力的非线性拓扑引擎"**。

两大核心演进方向：
1. **逻辑梯度注入 (Logical Gradients)** — 结构化的程序性反馈替代原始文本字符串
2. **动态图外科手术 (Dynamic Graph Surgery)** — 局部子图重规划替代全局重试

---

```markdown
[SYSTEM OVERRIDE / ARCHITECTURAL DIRECTIVE V2.0: SOTA EVOLUTION]
TARGET AGENT: Claude Opus 4.6 (Expert Code Generation Mode)
AUTHORIZATION LEVEL: Elite AI Research Architect (AAAI/NeurIPS 2026 Oral Submission Protocol)
PROJECT CLASSIFICATION: PNSV Framework - Dynamic Topological Replanning

ATTENTION CLAUDE OPUS 4.6:
I confirm you have internalized the Phase 1 blueprint (Polymorphic Bus, Domain-Agnostic BDI Engine, R1 Distillation). We are now executing PHASE 2. 

The baseline "Global Retry" mechanism is obsolete. It causes Epistemic Deadlock, Context Dilution (The Ablation Paradox), and Representation Collapse in SWE-bench due to long-horizon state space explosion. You must refactor the core modules to implement **Dynamic Sub-graph Replanning (Graph Surgery)** driven by **Logical Gradients** (structured, programmatic feedback replacing raw text strings).

Execute the following exact modifications. Do not hallucinate. Maintain 100% adherence to Pydantic V2, Python 3.10+ typing, and ZERO DOMAIN LEAKAGE in the core engine.

======================================================
STEP 1: DIMENSIONAL ELEVATION OF SCHEMAS (src/core/schemas.py)
======================================================
The IntentionDAG must transition from a static list to a runtime-aware, mutable Execution Forest.

1. Add `NodeStatus` Enum: PENDING, EXECUTING, SUCCESS, FAILED, SUSPENDED.
2. Create `LogicalGradient` BaseModel to replace pure string errors.
3. Update `IntentionNode` to track status.
4. Update `IntentionDAG` to use a dictionary for O(1) node lookups and add surgery methods.

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum

class NodeStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SUSPENDED = "SUSPENDED"

class LogicalGradient(BaseModel):
    """Structured Epistemic Delta replacing raw traceback strings."""
    failed_node_id: str
    missing_preconditions: Dict[str, Any] = Field(description="The exact state delta (ΔS) mathematically required.")
    conflicting_states: Dict[str, Any] = Field(description="The physical reality blocking the execution.")
    target_objective: str = Field(description="Synthesized objective for the bridging sub-graph.")

class IntentionNode(BaseModel):
    node_id: str
    action_type: str
    parameters: Dict[str, Any]
    dependencies: List[str] = Field(default_factory=list)
    status: NodeStatus = Field(default=NodeStatus.PENDING)

class IntentionDAG(BaseModel):
    dag_id: str
    nodes: Dict[str, IntentionNode] # Changed from List to Dict mapped by node_id
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # CLAUDE MUST IMPLEMENT:
    # def get_topological_descendants(self, node_id: str) -> List[str]:
    # def stitch_bridging_dag(self, bridging_dag: 'IntentionDAG', failed_node_id: str) -> None:
    # WARNING: stitching must NOT introduce cyclic dependencies (DAG cycles).
```

======================================================
STEP 2: POLYMORPHIC BUS UPGRADE (src/core/verification_bus.py)
======================================================
Shift from "Global DAG Verification" to "Topological Node-by-Node Verification". The bus must calculate the State Delta (ΔS).

```python
from abc import ABC, abstractmethod
from typing import Tuple, Optional
from src.core.schemas import BeliefState, IntentionNode, LogicalGradient

class BaseDomainVerifier(ABC):
    @abstractmethod
    def verify_and_simulate_node(self, current_belief: BeliefState, node: IntentionNode) -> Tuple[bool, Optional[LogicalGradient]]:
        """
        Validates a SINGLE node execution topologically against the current_belief.
        Returns (True, None) if successful.
        Returns (False, LogicalGradient) if formal constraints are violated.
        MUST NOT return raw strings. MUST NOT CONTAIN LLM CALLS.
        """
        pass
        
    @abstractmethod
    def commit_node_effects(self, current_belief: BeliefState, node: IntentionNode) -> None:
        """Applies the deterministic effects of a successful node to mutate the BeliefState IN PLACE."""
        pass
```

======================================================
STEP 3: THE HEART SURGERY - BDI ENGINE (src/core/bdi_engine.py)
======================================================
Eradicate the global retry loop. Implement Topological Wavefront Execution and Graph Surgery.

**Core Algorithmic Requirement for `BDIEngine.run()`:**

1. **Topological Runner**: Initialize a `graphlib.TopologicalSorter` or custom BFS/DFS for the `IntentionDAG`. Execute nodes where all dependencies have `status == SUCCESS`.
2. **On Success**: Call `commit_node_effects()`, mark node as `SUCCESS`, and advance the wavefront.
3. **On Failure (The Surgery Trigger)**: If `verify_and_simulate_node` returns `False` and a `LogicalGradient`:
   * Mark node N_f as `FAILED`.
   * Find all topological descendants of N_f and mark them `SUSPENDED`.
   * **Epistemic Pruning**: Do NOT pass massive traces. Prompt the DSPy Teacher, passing ONLY the `BeliefState` (at the exact point of failure) and the `LogicalGradient`. Request a `BridgingDAG`.
   * **Graph Stitching**: Call `dag.stitch_bridging_dag()`. Link the `BridgingDAG` roots to the original dependencies of N_f, and make N_f depend on the leaf nodes of the `BridgingDAG`.
   * Reset N_f to `PENDING`.
   * Recompute the topological sort and resume execution. Catch `CycleError` to prevent infinite loops.

======================================================
STEP 4: R1 ALIGNMENT & DSPY SIGNATURES (src/dspy_pipeline/)
======================================================
DeepSeek-R1-Distill must learn this localized backtracking natively.

1. **In `signatures.py`**: Create `GenerateBridgingDAG(dspy.Signature)` accepting `current_belief`, `failed_intention`, and `logical_gradient`, outputting `causal_rationale` and `bridging_dag_json`.
2. **In `r1_formatter.py`**: Update the formatter to intercept surgery events and format them strictly inside the `<think>` tag:

```text
<think>
[Topological Execution Wavefront]:
Successfully executed prefix nodes. Interrupted at Node '{failed_node_id}'.

[Logical Gradient Analysis]:
Missing State (ΔS): {logical_gradient.missing_preconditions}
Blocking State / Conflict: {logical_gradient.conflicting_states}
Target Objective: {logical_gradient.target_objective}

[Graph Surgery / Local Replanning Rationale]:
Global replanning is inefficient. I will suspend downstream nodes and generate a local Bridging DAG to satisfy ΔS without destroying protected subgoals.
{causal_rationale}
</think>
{strict_json_of_the_BRIDGING_DAG_only}
```

### FINAL EXECUTION PROTOCOL

Claude Opus 4.6, acknowledge Phase 2. Your immediate task is to generate the complete, production-ready Python code for `schemas.py`, `verification_bus.py`, `bdi_engine.py`, `signatures.py`, and `r1_formatter.py`.
Prove your elite engineering capability by implementing the DAG stitching logic (`stitch_bridging_dag`) and the topological execution loop flawlessly. Stand by to output code.
```

---

## 为什么这套 Prompt 能直接榨干 Claude 4.6 的极限

1. **绝对收束防幻觉（Preventing Hallucination）**：通过严格约束 `schemas.py` 和 `verification_bus.py` 的 I/O 类型签名，彻底堵死了 Claude 不小心越权去写"特定领域逻辑"的可能性（例如把 Pytest 的 regex 解析混入 Engine），强迫它将全部上下文注意力（Attention）集中在抽象的图操作算法上。

2. **点名核心算法难点（Algorithmic Hard-Constraints）**：在 Step 3 中，直接指出"避免环路（Cyclic dependencies）"和"依赖重组（Dependency rewiring）"是考核它架构能力的重点，并提示使用 `graphlib.TopologicalSorter`。这会触发大模型生成代码时最谨慎的"慢思考模式（System 2）"，大幅降低在审查拼接 DAG 时的工程 Bug 率。

3. **完美闭环 R1 蒸馏（Distillation Alignment）**：通过 Step 4，强制大模型的输出不仅为了让当前系统跑通，更是为了生成高质量的 RL 训练语料。明确的 `<think>` 标签结构，将把传统的确定性图修复算法，无缝转化为 DeepSeek-R1 能够模仿学习（Imitation Learning）的 CoT 推理模式。

---

**END OF PHASE 2 DIRECTIVE.**
