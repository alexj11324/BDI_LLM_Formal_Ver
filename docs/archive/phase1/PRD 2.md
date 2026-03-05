# PRD: PNSV (Pluggable Neuro-Symbolic Verification) Framework

## Overview

Build a domain-agnostic Belief-Desire-Intention (BDI) reasoning engine that uses a Polymorphic Verification Bus to validate LLM-generated intention DAGs across disparate domains (PlanBench & SWE-bench). The system generates verified "Golden Trajectories" via GLM-5/DSPy, serialized into `<think>` tag format for distilling a local DeepSeek-R1-Distill-Qwen-7B student model.

## Architecture Constraints

- **Zero Domain Leakage**: `src/core/bdi_engine.py` MUST NOT import `pytest`, `ast`, or `pddl`. Only generic dicts, Pydantic DAGs, and `BaseDomainVerifier`.
- **State Immutability**: Verifiers evaluate deep copies of BeliefState. Only commit on `is_valid == True`.
- **Strategy Pattern**: Domain logic lives only in plugins, injected via dependency injection.
- **Pydantic V2**: All schemas must use Pydantic V2.
- **Python 3.10+ type hints**: Every function/method must have strict type hints.

---

## Task 1: Project Scaffolding

Create the exact directory tree:

```
pnsv_workspace/
├── requirements.txt
├── src/
│   ├── core/
│   │   ├── __init__.py
│   │   ├── schemas.py
│   │   ├── verification_bus.py
│   │   ├── exceptions.py
│   │   └── bdi_engine.py
│   ├── plugins/
│   │   ├── __init__.py
│   │   ├── planbench_verifier.py
│   │   └── swe_verifier.py
│   └── dspy_pipeline/
│       ├── __init__.py
│       ├── teacher_config.py
│       ├── signatures.py
│       └── r1_formatter.py
└── tests/
    └── __init__.py
```

Create `requirements.txt` with: pydantic>=2.0, dspy-ai, openai, pytest.

---

## Task 2: Core Schemas (`src/core/schemas.py`)

Implement strict Pydantic V2 models:

- `IntentionNode`: node_id (str), action_type (str), parameters (Dict[str, Any]), dependencies (List[str]).
- `IntentionDAG`: dag_id (str), nodes (List[IntentionNode]), metadata (Dict[str, Any]).
- `BeliefState`: environment_context (Dict[str, Any]), epistemic_flags (Dict[str, Any]), suspended_intentions (List[IntentionDAG]).

---

## Task 3: Custom Exceptions (`src/core/exceptions.py`)

Create `EpistemicDeadlockError(Exception)` with attributes for failed_intention (IntentionDAG), retry_count (int), compressed_traces (List[str]).

---

## Task 4: Polymorphic Verification Bus (`src/core/verification_bus.py`)

Implement the `BaseDomainVerifier` abstract class:

- Abstract method `verify_transition(current_belief: BeliefState, intention_dag: IntentionDAG) -> Tuple[bool, str, str]`.
- Returns: (is_valid, formal_error_trace, dspy_correction_hint).
- MUST NOT contain LLM generation logic.

---

## Task 5: BDI Engine (`src/core/bdi_engine.py`)

Implement `BDIEngine` class:

- Constructor accepts `BaseDomainVerifier` and a DSPy teacher module (dependency injection).
- `extract_json_dag(raw_response: str) -> dict` utility: regex-based extraction (first `{` to last `}`), `json.loads` fallback. On failure, treat as verification failure.
- Main loop logic:
  1. Pop top Desire/Goal from queue.
  2. Prompt Teacher LLM to generate IntentionDAG.
  3. Pass deep copy of BeliefState + IntentionDAG to `self.verifier.verify_transition()`.
  4. On success: execute DAG, update BeliefState permanently, log Golden Trajectory.
  5. On failure: inject error traces + correction hints into context, increment retry counter, loop.
- **Epistemic Deadlock Guard**: If `retries > MAX_RETRIES` (default 3), raise `EpistemicDeadlockError`. Catch it, suspend task by pushing to `BeliefState.suspended_intentions`, compress failed traces into epistemic memory flag, force Teacher LLM to generate recovery plan.
- **Constraint**: NO domain-specific logic. No `if domain == "swe"` or similar.

---

## Task 6: PlanBench Verifier Plugin (`src/plugins/planbench_verifier.py`)

Implement `PlanBenchVerifier(BaseDomainVerifier)`:

- Forward-search state simulator for PDDL Blocksworld.
- Iterate topologically through IntentionDAG nodes.
- For actions like `unstack(A, B)`: check `clear(A)` and `on(A, B)` in `current_belief.environment_context['pddl_state']`.
- Generate structured failure traces:
  - `formal_error_trace = "PreconditionViolation: clear(A) is False at node_2"`
  - `dspy_correction_hint = "You attempted to unstack A from B, but A is not clear..."`

---

## Task 7: SWE-bench Verifier Plugin (`src/plugins/swe_verifier.py`)

Implement `SWEVerifier(BaseDomainVerifier)`:

- Action nodes contain file edits: target_file, search_string, replace_string.
- Write edits to a temporary sandbox directory (tempfile).
- Execute `subprocess.run(["pytest", "tests/"], capture_output=True, text=True)` in sandbox.
- Return pytest stderr as formal_error_trace on failure.
- Generate structured correction hints referencing the specific test failures.

---

## Task 8: DSPy Teacher Configuration (`src/dspy_pipeline/teacher_config.py`)

Implement `init_glm5_teacher(api_key: str, api_base: str) -> dspy.LM`:

- Configure DSPy to use GLM-5 via OpenAI-compatible interface.
- Default api_base: `https://open.bigmodel.cn/api/paas/v4/`.
- Use `dspy.LM(model='openai/glm-4', ...)`.

---

## Task 9: DSPy Signatures (`src/dspy_pipeline/signatures.py`)

Define DSPy Signatures that force structured BDI reasoning:

- `BDIReasoningSignature`: Takes belief_state, desire, domain_context → produces reasoning, intention_dag_json.
- `ErrorCorrectionSignature`: Takes belief_state, failed_dag, error_trace, correction_hint → produces corrected_dag_json.
- `RecoveryPlanSignature`: Takes suspended_intentions, epistemic_flags → produces recovery_plan_json.

---

## Task 10: R1 Distillation Formatter (`src/dspy_pipeline/r1_formatter.py`)

Implement `format_trajectory_for_r1()`:

- Intercept successful BDI loops.
- Serialize to `.jsonl` with strict `<think>` tag format:
  ```
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
- NO Markdown code blocks around final JSON.
- Write to `.jsonl` file line by line.

---

## Task 11: Unit Tests

Write tests in `tests/` for:

- Schema validation (valid/invalid IntentionDAGs).
- JSON extraction robustness (markdown artifacts, conversational filler).
- PlanBench verifier precondition checking.
- SWE verifier sandbox execution.
- Epistemic Deadlock triggering and task suspension.
- R1 formatter output compliance.
