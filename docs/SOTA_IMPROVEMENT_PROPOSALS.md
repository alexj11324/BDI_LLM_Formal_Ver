# SOTA Improvement Proposals for BDI-LLM Formal Verification Framework

**Date**: 2026-02-03
**Based on**: Code Review of BDI-LLM Framework v1.0
**Current Status**: 93.75% success rate, 75% structural accuracy

---

## Executive Summary

This document proposes state-of-the-art (SOTA) methods for improving the evaluation and training of the BDI-LLM agent planning system. Based on comprehensive code review, we identify key areas for enhancement and recommend cutting-edge techniques from recent research.

---

## Part 1: SOTA Evaluation Methods

### 1.1 AgentBench-Style Multi-Dimensional Evaluation

**Reference**: AgentBench (Liu et al., 2023)

**Current Gap**: The framework only evaluates structural correctness (DAG validity), lacking semantic and task completion metrics.

**Proposed Implementation**:

```python
class AgentBenchEvaluator:
    """
    Multi-dimensional evaluation framework inspired by AgentBench.
    """

    def evaluate(self, plan: BDIPlan, ground_truth: BDIPlan) -> Dict:
        return {
            # Structural Metrics (Current)
            "dag_validity": self.check_dag_validity(plan),
            "connectivity": self.check_connectivity(plan),

            # Semantic Metrics (New)
            "goal_alignment": self.measure_goal_alignment(plan, ground_truth),
            "action_coverage": self.calculate_action_coverage(plan, ground_truth),
            "dependency_precision": self.calculate_edge_precision(plan, ground_truth),
            "dependency_recall": self.calculate_edge_recall(plan, ground_truth),

            # Efficiency Metrics (New)
            "plan_length_ratio": len(plan.nodes) / len(ground_truth.nodes),
            "critical_path_length": self.calculate_critical_path(plan),

            # Robustness Metrics (New)
            "retry_count": self.count_retries(),
            "first_try_success": self.is_first_try_success()
        }
```

**Evaluation Dimensions**:

| Dimension | Metric | Description |
|-----------|--------|-------------|
| Structural | DAG Validity | Is the plan a valid DAG? |
| Structural | Weak Connectivity | Are all nodes connected? |
| Semantic | Goal Alignment | Does the plan achieve the stated goal? |
| Semantic | Action Coverage | Are all necessary actions included? |
| Semantic | Dependency F1 | Precision and recall of dependencies |
| Efficiency | Plan Optimality | Is the plan length reasonable? |
| Robustness | First-Try Rate | Success rate without retries |

### 1.2 LM-Evaluation-Harness Integration

**Reference**: EleutherAI lm-evaluation-harness

**Proposed Integration**:

```python
# tasks/bdi_planning.yaml
task: bdi_planning
dataset_path: local
dataset_name: bdi_scenarios
output_type: generate_until
doc_to_text: "Beliefs: {{beliefs}}\nDesire: {{desire}}\nPlan:"
doc_to_target: "{{plan_json}}"
metric_list:
  - metric: structural_accuracy
    aggregation: mean
  - metric: semantic_similarity
    aggregation: mean
  - metric: execution_feasibility
    aggregation: mean
```

**Benefits**:
- Standardized evaluation across different LLMs
- Easy comparison with baselines (GPT-4, Gemini, Llama)
- Integration with existing benchmark ecosystem

### 1.3 BEHAVIOR-1K Metrics for Embodied Planning

**Reference**: BEHAVIOR-1K (Li et al., 2023)

**Proposed Metrics**:

```python
class BehaviorMetrics:
    """
    Embodied AI planning metrics inspired by BEHAVIOR-1K.
    """

    def calculate_metrics(self, plan: BDIPlan, execution_trace: List) -> Dict:
        return {
            # Task Success
            "task_success_rate": self.check_goal_achieved(execution_trace),

            # Partial Credit
            "subgoal_completion": self.count_completed_subgoals(execution_trace),

            # Efficiency
            "action_efficiency": self.optimal_actions / self.actual_actions,
            "time_efficiency": self.optimal_time / self.actual_time,

            # Safety (Critical for robots)
            "constraint_violations": self.count_violations(execution_trace),
            "precondition_failures": self.count_precondition_failures(execution_trace)
        }
```

### 1.4 LLM-as-Judge for Semantic Evaluation

**Reference**: Zheng et al. (2023) "Judging LLM-as-a-Judge"

**Implementation**:

```python
class LLMJudgeEvaluator:
    """
    Use a stronger LLM to evaluate plan quality.
    """

    JUDGE_PROMPT = """
    You are an expert BDI planning evaluator.

    Given:
    - Beliefs (World State): {beliefs}
    - Desire (Goal): {desire}
    - Generated Plan: {plan}

    Evaluate the plan on a scale of 1-10 for:
    1. Goal Achievement: Does the plan achieve the goal?
    2. Logical Coherence: Are dependencies correctly ordered?
    3. Completeness: Are all necessary actions included?
    4. Efficiency: Is the plan optimally short?
    5. Safety: Does the plan avoid dangerous states?

    Output JSON with scores and justifications.
    """

    def evaluate(self, beliefs: str, desire: str, plan: BDIPlan) -> Dict:
        response = self.judge_lm(
            self.JUDGE_PROMPT.format(
                beliefs=beliefs,
                desire=desire,
                plan=plan.model_dump_json()
            )
        )
        return parse_judge_response(response)
```

**Evaluation Protocol**:
1. Generate plan with target LLM
2. Pass to judge LLM (e.g., Claude Opus 4 or GPT-4)
3. Aggregate scores across multiple scenarios
4. Report inter-rater reliability if using multiple judges

---

## Part 2: SOTA Training Methods

### 2.1 DSPy MIPRO Optimization

**Reference**: DSPy MIPRO (Khattab et al., 2024)

**Current Status**: The framework uses basic DSPy assertions but not optimization.

**Proposed Training Pipeline**:

```python
from dspy.teleprompt import MIPRO

class BDIPlannerOptimized(dspy.Module):
    def __init__(self):
        super().__init__()
        self.generate_plan = dspy.TypedPredictor(GeneratePlan)

    def forward(self, beliefs: str, desire: str) -> dspy.Prediction:
        pred = self.generate_plan(beliefs=beliefs, desire=desire)
        # Verification logic...
        return pred

# Training dataset
trainset = [
    dspy.Example(
        beliefs="Location: Living Room. Door: locked. Keys: on table.",
        desire="Go to kitchen",
        plan=valid_kitchen_plan  # Ground truth
    ).with_inputs("beliefs", "desire"),
    # ... more examples
]

# Metric function
def plan_metric(example, pred, trace=None):
    plan = pred.plan
    G = plan.to_networkx()
    is_valid, _ = PlanVerifier.verify(G)

    # Structural score (40%)
    structural_score = 1.0 if is_valid else 0.0

    # Semantic score (60%) - compare with ground truth
    semantic_score = compute_semantic_similarity(plan, example.plan)

    return 0.4 * structural_score + 0.6 * semantic_score

# Optimize
optimizer = MIPRO(metric=plan_metric, num_threads=4)
optimized_planner = optimizer.compile(
    BDIPlannerOptimized(),
    trainset=trainset,
    num_batches=10,
    max_bootstrapped_demos=3,
    max_labeled_demos=5
)
```

**Expected Improvements**:
- Auto-generated few-shot examples
- Optimized prompt instructions
- Higher first-try success rate

### 2.2 GRPO (Group Relative Policy Optimization)

**Reference**: DeepSeek-R1, Shao et al. (2024)

**Why GRPO**: Particularly effective for structured generation tasks with verifiable rewards.

**Proposed Implementation**:

```python
class GRPOTrainer:
    """
    Group Relative Policy Optimization for BDI planning.
    """

    def __init__(self, base_model, verifier: PlanVerifier):
        self.model = base_model
        self.verifier = verifier

    def compute_reward(self, plan: BDIPlan) -> float:
        """
        Reward function combining structural and semantic scores.
        """
        G = plan.to_networkx()
        is_valid, errors = self.verifier.verify(G)

        # Base reward for validity
        reward = 1.0 if is_valid else -1.0

        # Bonus for efficiency
        if is_valid:
            critical_path = nx.dag_longest_path_length(G)
            efficiency_bonus = 1.0 / (1.0 + critical_path * 0.1)
            reward += efficiency_bonus

        # Penalty for specific errors
        for error in errors:
            if "cycle" in error.lower():
                reward -= 0.5  # Cycles are critical errors
            if "disconnected" in error.lower():
                reward -= 0.3  # Disconnection is recoverable

        return reward

    def train_step(self, batch: List[Example]) -> Dict:
        """
        GRPO training step with group-relative advantages.
        """
        # Generate multiple plans per example (group)
        group_size = 4
        all_plans = []
        all_rewards = []

        for example in batch:
            plans = [self.model.generate(example) for _ in range(group_size)]
            rewards = [self.compute_reward(p) for p in plans]
            all_plans.extend(plans)
            all_rewards.extend(rewards)

        # Compute group-relative advantages
        advantages = self.compute_group_advantages(all_rewards, group_size)

        # Policy gradient update
        loss = self.policy_gradient_loss(all_plans, advantages)
        return {"loss": loss, "mean_reward": np.mean(all_rewards)}
```

**Training Configuration**:

```yaml
# grpo_config.yaml
training:
  group_size: 4
  batch_size: 8
  learning_rate: 1e-5
  num_epochs: 10
  kl_coefficient: 0.1

reward:
  validity_weight: 0.5
  efficiency_weight: 0.2
  semantic_weight: 0.3

model:
  base: "claude-opus-4-20250514-v1:0"
  adapter: "lora"
  rank: 16
```

### 2.3 Constitutional AI for Safe Planning

**Reference**: Anthropic Constitutional AI (Bai et al., 2022)

**Why Constitutional AI**: Ensures generated plans are safe and avoid dangerous action sequences.

**Proposed Constitution**:

```python
PLANNING_CONSTITUTION = [
    # Safety Rules
    {
        "principle": "Plans must never include actions that could harm humans.",
        "critique_request": "Does this plan include any potentially harmful actions?",
        "revision_request": "Remove or modify any harmful actions."
    },
    {
        "principle": "Plans must respect physical constraints and preconditions.",
        "critique_request": "Does this plan violate any physical laws or preconditions?",
        "revision_request": "Fix the plan to respect all preconditions."
    },
    {
        "principle": "Plans must be executable in a single sequential or parallel flow.",
        "critique_request": "Is this plan graph connected and cycle-free?",
        "revision_request": "Add necessary connections to make the graph weakly connected."
    },

    # Efficiency Rules
    {
        "principle": "Plans should be as short as possible while achieving the goal.",
        "critique_request": "Are there redundant actions in this plan?",
        "revision_request": "Remove redundant actions."
    },

    # Parallel Task Rules (Addresses known weakness)
    {
        "principle": "Parallel tasks must share a common start and synchronization point.",
        "critique_request": "Do parallel branches have proper fork-join structure?",
        "revision_request": "Add START and JOIN nodes for parallel branches."
    }
]

class ConstitutionalPlanner:
    def generate_with_constitution(self, beliefs: str, desire: str) -> BDIPlan:
        # Initial generation
        plan = self.base_planner(beliefs, desire)

        # Constitutional critique and revision
        for rule in PLANNING_CONSTITUTION:
            critique = self.critique_model(
                plan=plan,
                question=rule["critique_request"]
            )

            if critique.indicates_violation:
                plan = self.revision_model(
                    plan=plan,
                    instruction=rule["revision_request"]
                )

        return plan
```

### 2.4 DPO (Direct Preference Optimization)

**Reference**: Rafailov et al. (2023)

**Why DPO**: Simpler than RLHF, directly learns from preference pairs.

**Data Collection Strategy**:

```python
class PreferenceDataCollector:
    """
    Collect preference pairs for DPO training.
    """

    def collect_preferences(self, scenario: Example) -> Tuple[BDIPlan, BDIPlan]:
        """
        Generate (chosen, rejected) plan pairs.
        """
        # Generate multiple candidate plans
        candidates = [self.planner(scenario) for _ in range(5)]

        # Rank by verification + semantic score
        scored = []
        for plan in candidates:
            G = plan.to_networkx()
            is_valid, _ = PlanVerifier.verify(G)

            score = 0.0
            if is_valid:
                score += 1.0
                # Add semantic scoring
                score += self.semantic_scorer(plan, scenario)

            scored.append((plan, score))

        scored.sort(key=lambda x: x[1], reverse=True)

        # Return best and worst
        chosen = scored[0][0]
        rejected = scored[-1][0]

        return chosen, rejected

# DPO Training
def dpo_loss(model, chosen, rejected, beta=0.1):
    """
    Direct Preference Optimization loss.
    """
    log_prob_chosen = model.log_prob(chosen)
    log_prob_rejected = model.log_prob(rejected)

    # Reference model log probs
    with torch.no_grad():
        ref_log_prob_chosen = ref_model.log_prob(chosen)
        ref_log_prob_rejected = ref_model.log_prob(rejected)

    # DPO objective
    log_ratio_chosen = log_prob_chosen - ref_log_prob_chosen
    log_ratio_rejected = log_prob_rejected - ref_log_prob_rejected

    loss = -torch.log(torch.sigmoid(beta * (log_ratio_chosen - log_ratio_rejected)))

    return loss.mean()
```

### 2.5 Verifier-Guided Search (VGS)

**Reference**: Process Reward Models (Lightman et al., 2023)

**Innovation**: Use the formal verifier as a reward signal during generation.

```python
class VerifierGuidedSearch:
    """
    Use formal verifier to guide beam search during plan generation.
    """

    def __init__(self, generator, verifier: PlanVerifier, beam_width: int = 4):
        self.generator = generator
        self.verifier = verifier
        self.beam_width = beam_width

    def generate(self, beliefs: str, desire: str) -> BDIPlan:
        # Initialize beams
        beams = [{"partial_plan": [], "score": 0.0}]

        while not all_complete(beams):
            new_beams = []

            for beam in beams:
                # Generate next action candidates
                candidates = self.generator.next_actions(
                    beliefs, desire, beam["partial_plan"]
                )

                for action in candidates:
                    new_plan = beam["partial_plan"] + [action]

                    # Verify partial plan
                    partial_graph = self.build_partial_graph(new_plan)
                    validity_score = self.verifier.partial_verify(partial_graph)

                    new_beams.append({
                        "partial_plan": new_plan,
                        "score": beam["score"] + validity_score
                    })

            # Keep top-k beams
            beams = sorted(new_beams, key=lambda x: x["score"], reverse=True)
            beams = beams[:self.beam_width]

        return self.finalize_plan(beams[0]["partial_plan"])
```

---

## Part 3: Implementation Roadmap

### Phase 1: Enhanced Evaluation (Week 1-2)

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Implement AgentBench metrics | High | 2 days | None |
| Add LLM-as-Judge evaluator | High | 2 days | None |
| Create benchmark dataset (20+ scenarios) | High | 3 days | None |
| Integrate with lm-eval-harness | Medium | 2 days | Benchmark dataset |

### Phase 2: DSPy Optimization (Week 3-4)

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Collect training examples (50+) | High | 3 days | Benchmark dataset |
| Implement MIPRO training | High | 3 days | Training examples |
| Add few-shot examples for parallel tasks | High | 1 day | None |
| Benchmark optimized vs base | Medium | 2 days | MIPRO training |

### Phase 3: Advanced Training (Week 5-8)

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Implement preference data collection | Medium | 3 days | Evaluation metrics |
| DPO fine-tuning pipeline | Medium | 5 days | Preference data |
| Constitutional AI integration | Low | 3 days | None |
| Verifier-guided search | Low | 4 days | None |

### Phase 4: Robustness & Deployment (Week 9-12)

| Task | Priority | Effort | Dependencies |
|------|----------|--------|--------------|
| Multi-LLM benchmarking | Medium | 3 days | lm-eval integration |
| Parallel task fix (fork-join) | High | 2 days | None |
| Real robot integration (ROS) | Low | 2 weeks | Full pipeline |
| Documentation & paper draft | High | 1 week | All phases |

---

## Part 4: Expected Outcomes

### Quantitative Targets

| Metric | Current | Target | Method |
|--------|---------|--------|--------|
| Structural Accuracy | 75% | 95%+ | MIPRO + Parallel fix |
| Parallel Task Success | 0% | 80%+ | Fork-join prompting |
| First-Try Rate | 100% | 100% | Maintain |
| Semantic Score | N/A | 0.85+ | LLM-Judge |
| Average Retries | 0 | <0.5 | GRPO training |

### Qualitative Goals

1. **Reproducibility**: All experiments documented and reproducible
2. **Generalization**: Works across different planning domains
3. **Safety**: No unsafe plan ever executed
4. **Interpretability**: Clear explanations for plan structure

---

## Part 5: Key References

### Evaluation Methods
1. Liu et al. (2023). "AgentBench: Evaluating LLMs as Agents"
2. Li et al. (2023). "BEHAVIOR-1K: A Benchmark for Embodied AI"
3. Zheng et al. (2023). "Judging LLM-as-a-Judge"

### Training Methods
4. Khattab et al. (2024). "DSPy: Compiling Declarative Language Model Calls"
5. Shao et al. (2024). "DeepSeekMath: GRPO for Mathematical Reasoning"
6. Rafailov et al. (2023). "Direct Preference Optimization"
7. Bai et al. (2022). "Constitutional AI: Harmlessness from AI Feedback"
8. Lightman et al. (2023). "Let's Verify Step by Step" (Process Reward Models)

### BDI & Planning
9. Rao & Georgeff (1995). "BDI Agents: From Theory to Practice"
10. Wei et al. (2022). "Chain-of-Thought Prompting"

---

## Appendix: Code Templates

### A. Benchmark Scenario Template

```python
@dataclass
class BenchmarkScenario:
    id: str
    name: str
    complexity: Literal["simple", "medium", "complex", "parallel"]
    beliefs: str
    desire: str
    ground_truth_plan: Optional[BDIPlan]
    expected_actions: List[str]
    expected_min_edges: int
    tags: List[str]
```

### B. Evaluation Report Template

```python
@dataclass
class EvaluationReport:
    model_name: str
    timestamp: datetime
    total_scenarios: int
    passed_scenarios: int

    metrics: Dict[str, float]  # All computed metrics

    failure_cases: List[FailureCase]

    def to_markdown(self) -> str:
        ...
```

---

**Document Version**: 1.0
**Last Updated**: 2026-02-03
**Author**: AI Code Review Assistant
**Status**: Proposal (Pending Implementation)
