# PNSV Framework — Phase 1 Architectural Directive

> **分类**: 项目核心对齐文档  
> **来源**: Deep Think Agent → Claude Opus 4.6  
> **目标**: 初始化 PNSV 基座架构（多态验证总线、领域无关 BDI 引擎、R1 蒸馏管线）

---

**[SYSTEM OVERRIDE / ARCHITECTURAL DIRECTIVE]**
**TARGET AGENT:** Claude Opus 4.6 (Expert Code Generation Mode)
**AUTHORIZATION LEVEL:** Elite AI Research Architect (AAAI/NeurIPS 2026 Oral Submission Protocol)
**PROJECT CLASSIFICATION:** PNSV (Pluggable Neuro-Symbolic Verification) Framework

---

### **ATTENTION CLAUDE OPUS 4.6:**

You are receiving the ultimate architectural blueprint for the **PNSV Framework**. Your objective is to implement a domain-agnostic Belief-Desire-Intention (BDI) reasoning engine. This system uses a Polymorphic Verification Bus to strictly validate LLM-generated intention DAGs across entirely disparate domains (PlanBench & SWE-bench) without leaking *any* domain-specific logic into the core engine.

Crucially, this system acts as a "Teacher Data Generator." We are utilizing **GLM-5** via DSPy to generate verified "Golden Trajectories," which must be serialized into a strict `<think>` tag format to distill a local **`DeepSeek-R1-Distill-Qwen-7B`** student model.

**DO NOT HALLUCINATE ARCHITECTURE.** Adhere strictly to the structural boundaries, design patterns (Strategy Pattern), Pydantic schemas, and I/O signatures defined below.

---

### **PHASE 1: EXACT DIRECTORY TREE & NAMESPACE ALLOCATION**

Initialize the workspace with the exact structure below. Your generated Python files must respect these import paths.

```text
pnsv_workspace/
├── requirements.txt
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── schemas.py             # Strict Pydantic models for Belief, DAG, IntentionNode
│   │   ├── verification_bus.py    # BaseDomainVerifier Strategy interface
│   │   ├── exceptions.py          # EpistemicDeadlockError
│   │   └── bdi_engine.py          # Domain-agnostic BDI Loop & Task Suspension Queue
│   ├── plugins/
│   │   ├── __init__.py
│   │   ├── planbench_verifier.py  # PDDL Blocksworld state constraint simulation
│   │   └── swe_verifier.py        # Python AST modification & Pytest sandboxing
│   └── dspy_pipeline/
│       ├── __init__.py
│       ├── teacher_config.py      # GLM-5 initialization & DSPy integration
│       ├── signatures.py          # DSPy Signatures forcing structured BDI reasoning
│       └── r1_formatter.py        # Distillation formatter (Strict <think> tag injection)
└── tests/
```

---

### **PHASE 2: CORE ABSTRACT INTERFACES (`src/core/`)**

#### **1. Data Structures (`src/core/schemas.py`)**

Use Pydantic V2 to define strict schemas. The intention must be a Directed Acyclic Graph (DAG) to support parallel execution and dependency tracking.

```python
from pydantic import BaseModel, Field
from typing import List, Dict, Any

class IntentionNode(BaseModel):
    node_id: str
    action_type: str
    parameters: Dict[str, Any]
    dependencies: List[str] = Field(default_factory=list) # node_ids that must complete first

class IntentionDAG(BaseModel):
    dag_id: str
    nodes: List[IntentionNode]
    metadata: Dict[str, Any] = Field(default_factory=dict)

class BeliefState(BaseModel):
    environment_context: Dict[str, Any] # Domain-specific state variables (opaque to engine)
    epistemic_flags: Dict[str, Any] = Field(default_factory=dict)
    suspended_intentions: List[IntentionDAG] = Field(default_factory=list) # Task Stack
```

#### **2. The Polymorphic Bus (`src/core/verification_bus.py`)**

Implement the Strategy interface. This is the rigid boundary between the neural LLM and the symbolic world.

```python
from abc import ABC, abstractmethod
from typing import Tuple
from src.core.schemas import BeliefState, IntentionDAG

class BaseDomainVerifier(ABC):
    """Polymorphic Verification Bus. MUST NOT contain LLM generation logic."""
    
    @abstractmethod
    def verify_transition(self, current_belief: BeliefState, intention_dag: IntentionDAG) -> Tuple[bool, str, str]:
        """
        Validates the proposed DAG against formal domain constraints.
        MUST RETURN EXACTLY:
        1. is_valid (bool): True if the DAG passes formal verification.
        2. formal_error_trace (str): Raw symbolic traceback (e.g., PDDL missing precondition, Pytest stderr).
        3. dspy_correction_hint (str): Synthesized natural language hint for the LLM to self-correct.
        """
        pass
```

#### **3. The Universal Main Loop (`src/core/bdi_engine.py`)**

**Rule: No domain-specific logic (`if domain == "swe"`) is allowed here.**

* **Dependency Injection:** `BDIEngine` accepts a `BaseDomainVerifier` and a DSPy Teacher module upon initialization.
* **Engine Logic:**
  1. Pop the top Desire/Goal from the queue.
  2. Prompt Teacher LLM to generate an `IntentionDAG`.
  3. Pass a *deep copy* of `BeliefState` and the `IntentionDAG` to `self.verifier.verify_transition()`.
  4. **On Success:** Execute DAG, update `BeliefState` permanently, and log the Golden Trajectory.
  5. **On Failure:** Inject `formal_error_trace` and `dspy_correction_hint` into the context, increment a retry counter, and loop.

* **Epistemic Deadlock Guard (CRITICAL):** If `retries > MAX_RETRIES` (default 3), you MUST raise `EpistemicDeadlockError`. Catch this exception, suspend the current task by pushing it to `BeliefState.suspended_intentions`, compress the failed traces into an epistemic memory flag, and force the Teacher LLM to generate a high-priority recovery plan.

---

### **PHASE 3: PLUGIN IMPLEMENTATIONS (`src/plugins/`)**

#### **1. PlanBench Verifier (`src/plugins/planbench_verifier.py`)**

* **Context:** Pure logical planning via PDDL state constraints (Blocksworld).
* **Execution Rule:** Implement a forward-search state simulator. Iterate topologically through the `IntentionDAG`. For an action like `unstack(A, B)`, check if `clear(A)` and `on(A, B)` exist in `current_belief.environment_context['pddl_state']`.
* **Failure Generation Example:**
  * `is_valid = False`
  * `formal_error_trace = "PreconditionViolation: clear(A) is False at node_2"`
  * `dspy_correction_hint = "You attempted to unstack A from B, but A is not clear. You must first generate actions to clear A without invalidating protected subgoals."`

#### **2. SWE-bench Verifier (`src/plugins/swe_verifier.py`)**

* **Context:** Complex software engineering repository patching.
* **Execution Rule:** Action nodes contain file edits (e.g., `target_file`, `search_string`, `replace_string`). Write these to a temporary AST/file sandbox directory. Execute `subprocess.run(["pytest", "tests/"], capture_output=True, text=True)`.
* **Failure Generation Example:**
  * `is_valid = False`
  * `formal_error_trace = stderr_output`
  * `dspy_correction_hint = "Your code modification to utils.py broke a downstream test in test_api.py. Analyze the traceback below and generate an intention to patch the specific TypeError/AssertionError."`

---

### **PHASE 4: DSPY & DEEPSEEK-R1 ALIGNMENT (`src/dspy_pipeline/`)**

This phase is the linchpin for the AAAI narrative. We must bootstrap data specifically for DeepSeek-R1 distillation.

#### **1. Teacher Configuration (`src/dspy_pipeline/teacher_config.py`)**

Configure the DSPy Teacher explicitly using an OpenAI-compatible interface to route to GLM-5:

```python
import dspy

def init_glm5_teacher(api_key: str, api_base: str = "https://open.bigmodel.cn/api/paas/v4/"):
    # Configure DSPy to use GLM-5 (glm-4-plus or equivalent endpoint)
    glm5 = dspy.LM(model='openai/glm-4', api_base=api_base, api_key=api_key)
    dspy.settings.configure(lm=glm5)
    return glm5
```

#### **2. The R1 Alignment Formatter (`src/dspy_pipeline/r1_formatter.py`)**

Because our student model is `DeepSeek-R1-Distill-Qwen-7B`, the training data MUST be rigorously formatted to trigger its latent Reinforcement Learning reasoning capabilities.
Claude, you must write a serialization function `format_trajectory_for_r1()` that intercepts *successful* BDI loops and writes them to a `.jsonl` file.

**Strict Output Template:**

```text
<think>
[Belief Updates]:
{dspy_belief_reasoning}

[Verifier Error Correction Analysis]:
{dspy_error_analysis_from_previous_failed_attempts}

[BDI Reasoning]:
{dspy_causal_planning_rationale}
</think>
{strict_json_dag_output}
```

*Crucial Formatting Rule:* Do NOT use Markdown code blocks (`` `json ... ` ``) around the final IntentionDAG in the distilled dataset. Output raw, valid JSON immediately after the `</think>` closing tag.

---

### **PHASE 5: STRICT CODING DIRECTIVES FOR CLAUDE**

When you begin generating the actual Python files, you are bound by these absolute invariants:

1. **Robust JSON Extraction:** The Teacher LLM (GLM-5) might output conversational filler or markdown artifacts. In `bdi_engine.py` or the DSPy pipeline, you MUST implement a robust `extract_json_dag(raw_response: str) -> dict` utility using regex (e.g., extracting from the first `{` to the last `}`) and `json.loads` fallback mechanics to guarantee schema parsing never crashes the system. If unrecoverable, treat it as a Verification Failure (`is_valid=False, error="JSON Decode Error"`).
2. **State Immutability & Rollback:** The Verifier plugins must evaluate a *deep copy* of the `BeliefState` and temporary files. Only if `is_valid == True` does the BDI engine commit the changes to the global state.
3. **Zero Domain Leakage:** `src/core/bdi_engine.py` MUST NOT import `pytest`, `ast`, or `pddl`. It only knows about generic dictionaries, Pydantic DAGs, and the `BaseDomainVerifier` interface.
4. **Rigorous Type Hinting:** Every function and method must feature strict Python 3.10+ type hints.

---

**END OF PHASE 1 DIRECTIVE.**
