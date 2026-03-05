# C4 Component: BDI Engine

## Overview
| Property | Value |
|----------|-------|
| **Name** | BDI Engine |
| **Type** | Core Library |
| **Technology** | Python, Pydantic V2 |
| **Location** | [pnsv_workspace/src/core/bdi_engine.py](../pnsv_workspace/src/core/bdi_engine.py) |

## Purpose
Core orchestrator implementing the BDI (Belief-Desire-Intention) reasoning loop. Receives a natural language goal, generates an IntentionDAG via DSPy, verifies it through the Verification Bus, and iteratively repairs invalid plans. Manages BeliefState lifecycle with immutable verification (deep copies).

## Key Functions
- `generate_plan(goal, domain, context)` → IntentionDAG
- `verify_plan(dag, domain)` → VerificationResult
- `repair_plan(dag, errors, domain)` → IntentionDAG
- `run_bdi_loop(goal, domain, max_repairs=3)` → VerifiedPlan | Error
- Epistemic Deadlock detection and handling

## Dependencies
- **Internal**: Verification Bus, Schemas, DSPy Signatures
- **External**: None (zero domain leakage enforced)

---

# C4 Component: Verification Bus

## Overview
| Property | Value |
|----------|-------|
| **Name** | Verification Bus |
| **Type** | Core Library |
| **Technology** | Python |
| **Location** | [pnsv_workspace/src/core/verification_bus.py](../pnsv_workspace/src/core/verification_bus.py) |

## Purpose
Routes IntentionDAGs through a 3-layer verification pipeline. Layer 1 (Structural) runs domain-agnostic checks (empty graph, cycles, disconnected components). Layers 2-3 delegate to the registered BaseDomainVerifier (symbolic + physics). Short-circuits on first failure.

## Interfaces
- `register_verifier(domain: str, verifier: BaseDomainVerifier)`
- `verify(dag: IntentionDAG, domain: str) → VerificationResult`

## Dependencies
- **Internal**: Schemas (VerificationResult, VerificationLayer)
- **External**: None

---

# C4 Component: Domain Plugins

## Overview
| Property | Value |
|----------|-------|
| **Name** | Domain Plugins |
| **Type** | Plugin Library |
| **Technology** | Python, PDDL, VAL |
| **Location** | [pnsv_workspace/src/plugins/](../pnsv_workspace/src/plugins/) |

## Sub-components

### PlanBench Verifier
- **File**: `planbench_verifier.py`
- **Domains**: Blocksworld, Logistics, Depots
- **Layers**: VAL symbolic verification + domain physics simulation
- **External dep**: VAL binary (subprocess)

### SWE-bench Verifier
- **File**: `swe_verifier.py`
- **Domains**: Software engineering tasks
- **Actions**: read-file → edit-file → run-test
- **Verification**: File dependency checks, action sequencing

### Shared DAG Utilities
- **File**: `_dag_utils.py`
- **Functions**: `topological_sort()`, cycle detection, graph validation

---

# C4 Component: DSPy Pipeline

## Overview
| Property | Value |
|----------|-------|
| **Name** | DSPy Pipeline |
| **Type** | LLM Integration Layer |
| **Technology** | Python, DSPy |
| **Location** | [pnsv_workspace/src/dspy_pipeline/](../pnsv_workspace/src/dspy_pipeline/) |

## Sub-components

### Signatures (`signatures.py`)
DSPy ChainOfThought signature definitions for plan generation and repair.

### Teacher Configuration (`teacher_config.py`)
Multi-provider LLM configuration. Manages API keys, model selection (GLM-5, GPT-5, Gemini), and provider routing.

### R1 Distillation Formatter (`r1_formatter.py`)
Intercepts successful BDI reasoning loops and serializes into strict `<think>...</think><answer>...</answer>` format for student model fine-tuning.

## Dependencies
- **Internal**: Schemas
- **External**: LLM Provider APIs (HTTP/REST)
