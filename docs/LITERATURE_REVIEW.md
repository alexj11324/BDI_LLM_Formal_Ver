# Literature Review: SOTA Methods for LLM Agent Planning and Verification

**Date**: 2026-02-03
**Based on**: alphaXiv Paper Analysis
**Purpose**: Support SOTA improvement proposals for BDI-LLM Framework

---

## Executive Summary

This literature review examines recent advances in LLM agent evaluation and training methods, with focus on three key areas relevant to the BDI-LLM Formal Verification Framework:

1. **Process Reward Models (PRMs)** for step-by-step verification
2. **Agentic Evaluation Frameworks** (LLM-as-Judge evolution)
3. **Long-Horizon Planning Benchmarks** with automated verification

---

## 1. Process Reward Models: WebArbiter

**Paper**: WebArbiter (arXiv:2601.21872)
**Relevance**: Validates GRPO + PRM approach proposed in SOTA_IMPROVEMENT_PROPOSALS.md

### Key Findings

WebArbiter introduces a **Process Reward Model (PRM)** for web agent evaluation that scores individual actions rather than just final outcomes:

```
Traditional: Outcome Reward Model (ORM) → Binary success/failure
WebArbiter: Process Reward Model (PRM) → Step-by-step verification
```

### Training Pipeline (Two-Stage)

| Stage | Method | Purpose |
|-------|--------|---------|
| Stage 1 | SFT Distillation | Learn from Claude 3.5 Sonnet demonstrations |
| Stage 2 | GRPO (Reinforcement Learning) | Optimize with PRM feedback |

### Technical Architecture

- **Backbone Model**: Qwen2.5-7B
- **Reward Signal**: Multi-turn process rewards (not just final state)
- **Advantage**: Detects errors mid-execution, enabling early correction

### Application to BDI-LLM Framework

The PRM approach directly validates our proposed **Verifier-Guided Search (VGS)** method:

```python
# Current approach (from SOTA_IMPROVEMENT_PROPOSALS.md)
class VerifierGuidedSearch:
    def generate(self, beliefs, desire):
        for action in candidates:
            partial_graph = self.build_partial_graph(new_plan)
            validity_score = self.verifier.partial_verify(partial_graph)  # ← PRM concept
            # Score each step, not just final plan
```

**Key Insight**: WebArbiter's success with PRMs on web agents suggests similar step-by-step verification would improve BDI plan generation. The formal verifier can serve as an automated PRM.

---

## 2. Agentic Evaluation: Agent-as-a-Judge

**Paper**: Agent-as-a-Judge (arXiv:2601.05111)
**Relevance**: Extends LLM-as-Judge concept proposed in our evaluation methods

### Evolution from LLM-as-Judge

| Aspect | LLM-as-Judge | Agent-as-a-Judge |
|--------|--------------|------------------|
| Capability | Single prompt evaluation | Multi-step agentic workflow |
| Tools | None | External tool integration |
| Collaboration | Single model | Multi-agent deliberation |
| Granularity | Holistic scores | Fine-grained dimensions |

### Framework Components

1. **Tool Integration**: Evaluator agent can use external tools (code execution, search)
2. **Multi-Agent Collaboration**: Multiple specialist judges deliberate
3. **Fine-Grained Assessment**: Separate scores for different quality dimensions

### Application to BDI-LLM Framework

This extends our proposed `LLMJudgeEvaluator` (from SOTA_IMPROVEMENT_PROPOSALS.md):

```python
# Proposed enhancement based on Agent-as-a-Judge
class AgenticPlanEvaluator:
    """
    Multi-agent evaluation with tool use for BDI plan assessment.
    """

    def __init__(self):
        self.structure_agent = StructureEvaluator()  # Uses NetworkX
        self.semantic_agent = SemanticEvaluator()    # Uses LLM
        self.safety_agent = SafetyEvaluator()        # Domain constraints
        self.deliberation_agent = DeliberationAgent() # Aggregates

    def evaluate(self, plan: BDIPlan) -> Dict:
        # Parallel evaluation by specialist agents
        structure_score = self.structure_agent(plan)  # Tool: verifier.py
        semantic_score = self.semantic_agent(plan)    # Tool: LLM API
        safety_score = self.safety_agent(plan)        # Tool: domain rules

        # Multi-agent deliberation
        final_assessment = self.deliberation_agent.aggregate([
            structure_score,
            semantic_score,
            safety_score
        ])

        return final_assessment
```

**Key Insight**: The Agent-as-a-Judge paradigm suggests our evaluation should not just use a single LLM judge, but orchestrate multiple specialized evaluators with tool access (including our formal verifier).

---

## 3. Long-Horizon Planning: DeepPlanning

**Paper**: DeepPlanning (arXiv:2601.18137)
**Relevance**: Provides benchmark methodology for evaluating planning capabilities

### Benchmark Design

DeepPlanning evaluates LLM planning across two domains:

| Domain | Complexity | Key Challenges |
|--------|------------|----------------|
| Travel Planning | Medium | Multi-constraint optimization, resource management |
| Shopping Planning | High | Preference satisfaction, budget constraints |

### Evaluation Dimensions

1. **Proactive Information Acquisition**: Does the agent gather necessary information?
2. **Constrained Reasoning**: Does the plan satisfy all constraints?
3. **Global Optimization**: Is the plan globally optimal, not just locally valid?

### Automated Verification

DeepPlanning uses **code-based automated checkers** (not human evaluation):

```python
# DeepPlanning verification approach
def verify_travel_plan(plan, constraints):
    checks = [
        check_budget_constraint(plan, constraints.budget),
        check_time_constraint(plan, constraints.duration),
        check_location_feasibility(plan, constraints.locations),
        check_preference_satisfaction(plan, constraints.preferences)
    ]
    return all(checks), detailed_scores
```

### Application to BDI-LLM Framework

This directly validates our **benchmark design approach**:

| DeepPlanning Aspect | BDI-LLM Equivalent |
|---------------------|-------------------|
| Automated code-based checkers | `PlanVerifier.verify(G)` |
| Multi-constraint verification | DAG + Connectivity + Domain rules |
| Scalable benchmark | `run_evaluation.py --mode benchmark` |

**Proposed Enhancement**: Add domain-specific constraint checkers beyond graph validity:

```python
# Enhanced verification (inspired by DeepPlanning)
class EnhancedPlanVerifier:
    def verify(self, plan: BDIPlan, domain_constraints: Dict) -> Tuple[bool, List[str]]:
        errors = []

        # Structural verification (existing)
        G = plan.to_networkx()
        if not nx.is_weakly_connected(G):
            errors.append("Plan graph is disconnected")
        if list(nx.simple_cycles(G)):
            errors.append("Plan contains cycles")

        # Domain constraint verification (new, inspired by DeepPlanning)
        for constraint_name, checker in domain_constraints.items():
            if not checker(plan):
                errors.append(f"Constraint violated: {constraint_name}")

        return len(errors) == 0, errors
```

---

## 4. Synthesis: Recommended Enhancements

Based on this literature review, here are prioritized enhancements for the BDI-LLM framework:

### Priority 1: Process Reward Integration (from WebArbiter)

Convert the formal verifier into a step-by-step reward signal:

```python
def compute_process_reward(partial_plan: List[ActionNode]) -> float:
    """
    PRM-style reward for partial plan verification.
    """
    G = build_partial_graph(partial_plan)

    # Check partial DAG validity
    has_cycles = len(list(nx.simple_cycles(G))) > 0

    # Connectivity potential (will be connected when complete?)
    components = nx.number_weakly_connected_components(G)

    reward = 1.0
    if has_cycles:
        reward -= 0.5
    if components > 1:
        reward -= 0.2 * (components - 1)  # Partial penalty

    return reward
```

### Priority 2: Multi-Agent Evaluation (from Agent-as-a-Judge)

Implement specialist evaluator agents:

| Agent | Role | Tool Used |
|-------|------|-----------|
| StructureAgent | Graph validity | NetworkX verifier |
| SemanticAgent | Goal alignment | LLM (Claude) |
| EfficiencyAgent | Plan optimality | Graph algorithms |
| SafetyAgent | Constraint checking | Domain rules |

### Priority 3: Benchmark Expansion (from DeepPlanning)

Add new evaluation dimensions:

```yaml
# benchmark_config.yaml (enhanced)
evaluation_dimensions:
  - name: structural_validity
    weight: 0.3
    checker: verifier.py

  - name: goal_achievement
    weight: 0.3
    checker: semantic_evaluator.py

  - name: constraint_satisfaction
    weight: 0.2
    checker: domain_constraints.py

  - name: efficiency
    weight: 0.2
    checker: efficiency_evaluator.py
```

---

## 5. Key Citations

### Process Reward Models & GRPO

1. **WebArbiter** (2601.21872) - "Process reward models for web agent verification"
   - Key contribution: Two-stage training (SFT + GRPO) with step-by-step rewards
   - Relevance: Validates Verifier-Guided Search approach

2. **Lightman et al. (2023)** - "Let's Verify Step by Step"
   - Key contribution: Original PRM concept for mathematical reasoning
   - Relevance: Foundation for process-level verification

3. **Shao et al. (2024)** - "DeepSeekMath: GRPO for Mathematical Reasoning"
   - Key contribution: Group Relative Policy Optimization
   - Relevance: Already proposed in SOTA_IMPROVEMENT_PROPOSALS.md

### Agentic Evaluation

4. **Agent-as-a-Judge** (2601.05111) - "Agentic framework for AI evaluation"
   - Key contribution: Multi-agent collaborative evaluation with tools
   - Relevance: Extends LLM-as-Judge concept

5. **Zheng et al. (2023)** - "Judging LLM-as-a-Judge"
   - Key contribution: Original LLM-as-Judge methodology
   - Relevance: Baseline for evaluation methods

### Planning Benchmarks

6. **DeepPlanning** (2601.18137) - "Long-horizon planning benchmark"
   - Key contribution: Automated code-based plan verification
   - Relevance: Validates automated verification approach

7. **Liu et al. (2023)** - "AgentBench: Evaluating LLMs as Agents"
   - Key contribution: Multi-dimensional agent evaluation
   - Relevance: Already proposed in SOTA_IMPROVEMENT_PROPOSALS.md

---

## 6. Conclusion

This literature review confirms that the SOTA methods proposed in `SOTA_IMPROVEMENT_PROPOSALS.md` are well-aligned with cutting-edge research:

| Proposed Method | Validating Paper | Status |
|-----------------|------------------|--------|
| GRPO Training | WebArbiter | ✅ Validated |
| Process Reward Models | WebArbiter, Lightman et al. | ✅ Validated |
| LLM-as-Judge | Agent-as-a-Judge | ✅ Extended to Multi-Agent |
| Automated Verification | DeepPlanning | ✅ Validated |
| AgentBench Metrics | DeepPlanning | ✅ Validated |

**Recommended Next Steps**:

1. Implement PRM-based partial plan verification
2. Expand to multi-agent evaluation framework
3. Add domain-specific constraint checkers
4. Create benchmark scenarios matching DeepPlanning complexity

---

**Generated**: 2026-02-03
**Source**: alphaXiv API Queries
**Framework Version**: BDI-LLM v1.0
