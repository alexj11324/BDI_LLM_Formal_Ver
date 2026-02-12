# System Architecture

The BDI-LLM Framework implements a **neuro-symbolic planning architecture** that integrates Large Language Models (LLMs) with formal verification methods.

## Core Philosophy

Traditional LLM planning suffers from two critical issues:
1.  **Hallucination**: Generating valid-looking but logically impossible actions (e.g., picking up an object that isn't clear).
2.  **Structural Inconsistency**: Generating disconnected graph structures or cyclic dependencies.

This framework addresses these by treating the LLM as a **Generative Compiler**—translating natural language goals into formal BDI (Belief-Desire-Intention) structures—and using rigorous **Formal Verifiers** to validate the output.

## Architecture Overview

```mermaid
graph TD
    User[User Input] -->|Beliefs & Desire| Planner[LLM Planner]
    Planner -->|Draft Plan| Verifier{Multi-Layer Verifier}
    
    Verifier -->|Pass| Execution[Valid Plan]
    Verifier -->|Fail| Repair[Auto-Repair / Feedback]
    
    Repair -->|Refined Plan| Verifier
```

## Verification Layers

The system enforces validity through three distinct layers of verification:

### Layer 1: Structural Verification (Graph Theory)
Ensures the plan is a well-formed Directed Acyclic Graph (DAG).
*   **Checks**: Cycle detection, Weak connectivity, Topological sortability.
*   **Implementation**: `src/bdi_llm/verifier.py` using `networkx`.
*   **Role**: Prevents deadlock and ensures all actions are part of a cohesive plan.

### Layer 2: Symbolic Verification (PDDL)
Checks logical consistency against Planning Domain Definition Language (PDDL) rules.
*   **Checks**: Action preconditions (e.g., `(clear A)` before `(pickup A)`), Effect application.
*   **Tools**: Integrates with [VAL (Plan Validation Tool)](https://github.com/KCL-Planning/VAL).
*   **Role**: Guarantees that the plan is logically sound within the defined domain.

### Layer 3: Physics Validation (Domain-Specific)
Validates constraints that are difficult to express in pure PDDL or require simulation.
*   **checks**: Domain-specific physics rules (e.g., Blocksworld stability).
*   **Implementation**: `src/bdi_llm/verifier.py` (e.g., `BlocksworldPhysicsValidator`).
*   **Role**: Ensures executability in the target environment.

## Key Components

### 1. BDI Planner (`src/bdi_llm/planner.py`)
Uses **DSPy** to prompt the LLM with a structured signature. It maps:
*   **Beliefs**: Current state of the world.
*   **Desire**: The goal state.
*   **Intention**: The generated plan (graph of actions).

### 2. Auto-Repair System (`src/bdi_llm/plan_repair.py`)
A heuristic-based module that automatically fixes common structural errors without re-querying the LLM.
*   **Capabilities**: Connects disconnected subgraphs, unifies multiple root nodes, canonicalizes node IDs.

### 3. Integrated Verifier
Orchestrates the three verification layers and provides detailed error feedback.

## Data Flow

1.  **Input**: Natural language goal + Initial state.
2.  **Generation**: LLM output structured JSON (BDIPlan schema).
3.  **Graph Construction**: JSON converted to NetworkX DiGraph.
4.  **Verification**:
    *   If **Structure Fail**: Trigger Auto-Repair.
    *   If **Structure Pass**: Run Symbolic/Physics checkers.
5.  **Output**: Verified Plan or Error Report.
