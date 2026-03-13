# C4 Code-Level Details — BDI-LLM Formal Verification (PNSV)

## src/bdi_llm/planner/ — Core Planning Engine

### bdi_engine.py (~800 lines)

| Function/Class | Signature | Purpose |
|----------------|-----------|---------|
| `BDIPlanner` | `class BDIPlanner(domain_spec: DomainSpec)` | Main BDI planner — orchestrates goal decomposition and DAG construction |
| `BDIPlanner.generate` | `(task: PlanningTask) -> BDIPlan` | Generate a complete IntentionDAG from a planning task |
| `BDIPlanner._decompose_goal` | `(goal: str) -> list[SubGoal]` | Decompose high-level goal into sub-goals via DSPy |
| `BDIPlanner._generate_actions` | `(subgoal: SubGoal) -> list[ActionNode]` | Generate concrete actions for each sub-goal |

### domain_spec.py (~650 lines)

| Function/Class | Signature | Purpose |
|----------------|-----------|---------|
| `DomainSpec` | `@dataclass` | Pluggable domain configuration container |
| `DomainSpec.from_pddl` | `(pddl_text: str) -> DomainSpec` | Construct domain spec from raw PDDL text |
| `extract_domain_name_from_pddl` | `(pddl_text: str) -> str \| None` | Parse domain name from PDDL header |
| `_parse_typed_parameters` | `(raw: str) -> list[tuple[str,str]]` | Parse PDDL parameter declarations |

### signatures.py (~1200 lines)

All DSPy Signatures for plan generation, decomposition, and repair. Contains `GenerateBDIPlan`, `DecomposeGoal`, `GenerateActions`, `RepairPlan`, and domain-specific variants.

---

## src/bdi_llm/ — Verification & Repair

### symbolic_verifier.py (~550 lines)

| Function/Class | Signature | Purpose |
|----------------|-----------|---------|
| `PDDLSymbolicVerifier` | `class` | Layer 2 symbolic verification via VAL |
| `PDDLSymbolicVerifier.verify` | `(plan, domain_pddl, problem_pddl) -> VerificationResult` | Validate PDDL plan against domain constraints |
| `IntegratedVerifier` | `class` | Compose structural + symbolic + domain checks |

### plan_repair.py (~450 lines)

| Function/Class | Signature | Purpose |
|----------------|-----------|---------|
| `PlanRepairEngine` | `class` | Auto-repair engine with iterative error feedback |
| `PlanRepairEngine.repair` | `(plan, errors, max_iter=3) -> BDIPlan` | Repair invalid plan using verification error traces |

### planning_task.py (~430 lines)

| Function/Class | Signature | Purpose |
|----------------|-----------|---------|
| `PlanningTask` | `@dataclass` | Normalized task representation across all domains |
| `PDDLTaskAdapter` | `class` | Convert PDDL problem/domain to PlanningTask |
| `TravelPlannerTaskAdapter` | `class` | Convert TravelPlanner query to PlanningTask |

---

## src/bdi_llm/travelplanner/ — TravelPlanner Domain

### engine.py (~300 lines)
BDI itinerary generation engine with v3/v4 prompt variants.

### runner.py (~500 lines)
Evaluation runner with concurrent workers, checkpointing, and repair integration.

### review.py (~700 lines)
Stage 3 reviewer with patch-scope repair — evaluates itinerary quality and generates localized fixes.

### official.py (~200 lines)
Integration bridge to the official TravelPlanner evaluator scripts.

---

## src/bdi_llm/dynamic_replanner/ — Dynamic Replanning

### replanner.py (~160 lines)
Classical BDI replan loop: monitor execution → detect failure → regenerate sub-plan.

### belief_base.py (~130 lines)
Belief state management — tracks world state and detects state changes.

### executor.py (~90 lines)
Plan execution with failure detection and rollback capability.

---

## src/interfaces/ — External Interfaces

### mcp_server.py (~180 lines)
MCP server exposing `generate_plan`, `verify_plan`, `execute_verified_plan` tools via stdio transport.

### cli.py (~60 lines)
Interactive CLI entry point with argparse-based argument parsing.
