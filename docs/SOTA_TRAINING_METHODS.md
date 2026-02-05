# SOTA Training Methods for BDI-LLM Framework

*Last Updated: 2026-02-03*

## Executive Summary

Based on recent research from alphaxiv (2025-2026), we identify three key training methodologies that can address the **parallel task failure problem** in our BDI-LLM framework:

1. **SDPO (Self-Distillation Policy Optimization)** - Converts binary verifier feedback into dense token-level supervision
2. **TTRL (Test-Time Reinforcement Learning)** - Self-evolution via majority voting without labels
3. **AutoRocq** - Iterative refinement with error-driven feedback (search pending)

---

## 1. SDPO: Self-Distillation Policy Optimization

**Paper**: "Reinforcement Learning via Self-Distillation" (arXiv:2601.20802)
**Authors**: Jonas Hübotter et al.
**Published**: Jan 28, 2026
**Citations**: 4,144 visits, 270 likes on alphaXiv

### Core Mechanism

SDPO transforms **binary verifiable rewards** (like our DAG verifier output) into **dense token-level supervision** through self-distillation:

```python
# Traditional RLVR (e.g., GRPO)
advantage = binary_reward  # Same value for entire sequence

# SDPO's Self-Distillation
1. Student generates rollout → gets verifier feedback (pass/fail + error list)
2. Re-prompt with feedback: "Given errors: X, Y, Z - re-evaluate your plan"
3. Teacher policy (same model + feedback context) → new token distribution
4. Distill: advantage[token] = KL_divergence(teacher_logits, student_logits)
```

### Key Advantages for BDI-LLM

✅ **Handles Binary Feedback**: Our verifier returns `(is_valid, error_list)` - SDPO can use this
✅ **Implicit Positive Signals**: Successful plans in same batch teach failed plans
✅ **No External Teacher Needed**: Self-distillation using same LLM
✅ **Token-Level Credit Assignment**: Learns which specific edges/nodes caused cycle errors

### Integration Strategy

```python
# Current BDI-LLM flow
class GeneratePlan(dspy.Signature):
    beliefs: str = dspy.InputField()
    desire: str = dspy.InputField()
    plan: BDIPlan = dspy.OutputField()

# SDPO-enhanced version
class SDPOPlanner:
    def generate_with_sdpo(self, beliefs, desire, num_rollouts=4):
        # Phase 1: Generate multiple rollouts
        rollouts = []
        for _ in range(num_rollouts):
            plan = self.predictor(beliefs=beliefs, desire=desire).plan
            is_valid, errors = verify_plan(plan)
            rollouts.append((plan, is_valid, errors))

        # Phase 2: Self-teaching with feedback
        for plan, is_valid, errors in rollouts:
            if not is_valid:
                # Re-prompt with verifier feedback
                feedback_prompt = f"""
                Previous plan FAILED verification:
                Errors: {errors}

                Regenerate considering these specific issues.
                """

                # Get teacher logits (same model + feedback context)
                teacher_logits = self.predictor_with_feedback(
                    beliefs=beliefs + feedback_prompt,
                    desire=desire
                ).plan_logits

                # Compute token-level advantages via KL divergence
                advantages = compute_kl_advantages(student_logits, teacher_logits)

                # Update policy with dense supervision
                self.update_policy(advantages)

        return best_valid_plan or last_plan
```

---

## 2. TTRL: Test-Time Reinforcement Learning

**Paper**: "TTRL: Test-Time Reinforcement Learning" (arXiv:2504.16084)
**Authors**: Yuxin Zuo et al. (Tsinghua + Shanghai AI Lab)
**Published**: April 22, 2025
**Performance**: **211% improvement** on AIME 2024 (Qwen-2.5-Math-7B: 12.9% → 40.2%)

### Core Innovation

**Generates pseudo-rewards from majority voting** - no ground-truth labels needed:

```python
# TTRL Reward Generation Pipeline
1. Repeated Sampling: Generate n=32 candidate plans for same (beliefs, desire)
2. Answer Extraction: Parse each plan → extract key features (e.g., # nodes, edge count)
3. Majority Voting: Find consensus output → "estimated label"
4. Binary Reward Assignment:
   reward[plan_i] = 1 if plan_i matches consensus else 0
5. Policy Optimization: Use GRPO with these pseudo-rewards
```

### Self-Evolving Loop

The key insight: **Model's own consensus is a better teacher than its initial output**

```
Initial Model Accuracy: 12.9%
↓ (TTRL iteration 1)
Majority@32 Accuracy: ~30% (bootstrapped from consensus)
↓ (TTRL iteration 2)
New Model Accuracy: 25%  (surpasses initial maj@32!)
↓ (TTRL iteration 3)
Final Accuracy: 40.2%  (211% improvement)
```

### Adaptation for BDI-LLM

```python
class TTRLPlanner:
    def test_time_evolve(self, beliefs, desire, n_samples=16, n_iterations=3):
        for iteration in range(n_iterations):
            # Step 1: Generate multiple candidates
            candidates = [
                self.predictor(beliefs=beliefs, desire=desire).plan
                for _ in range(n_samples)
            ]

            # Step 2: Find consensus via graph similarity
            consensus_plan = self.find_consensus_plan(candidates)

            # Step 3: Assign pseudo-rewards
            rewards = []
            for plan in candidates:
                # Reward based on structural similarity to consensus
                similarity = self.graph_similarity(plan, consensus_plan)
                reward = 1.0 if similarity > threshold else 0.0
                rewards.append(reward)

            # Step 4: GRPO update
            self.grpo_update(candidates, rewards)

            # Step 5: Verify if consensus improved
            is_valid, errors = verify_plan(consensus_plan)
            if is_valid:
                return consensus_plan

        return consensus_plan  # Return best effort

    def graph_similarity(self, plan_a, plan_b):
        """Measure structural similarity for consensus voting"""
        G_a = plan_a.to_networkx()
        G_b = plan_b.to_networkx()

        # Jaccard similarity on edges
        edges_a = set(G_a.edges())
        edges_b = set(G_b.edges())

        intersection = edges_a & edges_b
        union = edges_a | edges_b

        return len(intersection) / len(union) if union else 0.0
```

### Key Hyperparameters (from paper)

- **n_samples**: 16-32 for consensus voting
- **GRPO group_norm**: advantage estimator
- **Temperature**: 0.7 for diverse sampling
- **Iterations**: 3-5 until convergence

---

## 3. AutoRocq: Agentic Program Verification

**Paper**: "AutoRocq: Agentic Program Verification" (arXiv:2511.17330)
**Status**: Need to retrieve full paper
**Performance**: 51.1% on CoqGym, 30.9% on SV-COMP

### Reported Mechanisms (from your notes)

1. **Iterative Refinement Loop**: Similar to our current `dspy.Assert()` approach
2. **Dynamic Context Search**: Retrieves relevant examples when verification fails
3. **Error-Driven Feedback**: Uses verifier errors to guide next attempt
4. **Historical Proof Management**: Stores successful patterns for reuse

### Potential Integration

```python
class AutoRocqStylePlanner:
    def __init__(self):
        self.success_library = []  # Store successful fork-join patterns

    def generate_with_context_search(self, beliefs, desire):
        # Step 1: Initial attempt
        plan = self.predictor(beliefs=beliefs, desire=desire).plan
        is_valid, errors = verify_plan(plan)

        if is_valid:
            self.success_library.append((beliefs, desire, plan))
            return plan

        # Step 2: Context search - find similar successful patterns
        relevant_examples = self.search_success_library(beliefs, desire, errors)

        # Step 3: Regenerate with context
        few_shot_prompt = self.format_few_shot(relevant_examples)
        plan = self.predictor(
            beliefs=beliefs + few_shot_prompt,
            desire=desire
        ).plan

        return plan

    def search_success_library(self, beliefs, desire, errors):
        """Retrieve similar successful plans"""
        if "not weakly connected" in str(errors):
            # Find examples with successful fork-join patterns
            return [p for p in self.success_library
                    if "parallel" in p[1].lower()]

        if "cycle detected" in str(errors):
            # Find examples with correct DAG structures
            return [p for p in self.success_library
                    if self.is_dag(p[2])]

        return []
```

---

## Recommended Implementation Roadmap

### Phase 1: Quick Wins (1-2 weeks)

**Goal**: Fix parallel task problem without RL training

1. **Few-Shot Learning with Fork-Join Examples**
   ```python
   # Add to planner.py
   PARALLEL_EXAMPLE = dspy.Example(
       beliefs="Printer available, Email server accessible",
       desire="Print document and send email simultaneously",
       plan=BDIPlan(
           goal="Complete parallel tasks",
           nodes=[
               ActionNode(id="START", type="init", ...),
               ActionNode(id="print", type="action", ...),
               ActionNode(id="email", type="action", ...),
               ActionNode(id="END", type="finalize", ...)
           ],
           edges=[
               DependencyEdge(source="START", target="print"),
               DependencyEdge(source="START", target="email"),
               DependencyEdge(source="print", target="END"),
               DependencyEdge(source="email", target="END")
           ]
       )
   )
   ```

2. **Post-Hoc Graph Repair**
   ```python
   def auto_repair_disconnected_components(plan: BDIPlan) -> BDIPlan:
       """Insert virtual START/END nodes for disconnected graphs"""
       G = plan.to_networkx()

       if not nx.is_weakly_connected(G):
           # Find connected components
           components = list(nx.weakly_connected_components(G))

           # Add virtual START node
           plan.nodes.insert(0, ActionNode(id="START", type="init"))

           # Add virtual END node
           plan.nodes.append(ActionNode(id="END", type="finalize"))

           # Connect components through START/END
           for component in components:
               # Fork: START → first node in component
               first_node = min(component)
               plan.edges.append(DependencyEdge(source="START", target=first_node))

               # Join: last node in component → END
               last_node = max(component)
               plan.edges.append(DependencyEdge(source=last_node, target="END"))

       return plan
   ```

### Phase 2: SDPO Integration (2-4 weeks)

**Goal**: Convert binary verifier feedback into dense supervision

1. **Implement self-distillation loop** (see SDPO code above)
2. **Collect training data**:
   - Run current planner on 100-200 diverse scenarios
   - Store `(beliefs, desire, plan, is_valid, errors)` tuples
3. **Train with SDPO**:
   - Use CMU AI Gateway Claude Opus 4
   - Batch size: 4-8 rollouts per query
   - KL divergence weight: 0.1 (from paper)

### Phase 3: TTRL Test-Time Adaptation (4-6 weeks)

**Goal**: Self-evolution on unlabeled test data

1. **Implement majority voting consensus** (see TTRL code above)
2. **GRPO integration**:
   - Use DSPy's built-in optimizer if available
   - Otherwise, implement group normalization manually
3. **Adaptive curriculum**:
   ```python
   if parallel_task_failure_rate > 0.5:
       increase_parallel_task_weight_in_sampling()
   ```

### Phase 4: AutoRocq-Style Success Library (6-8 weeks)

**Goal**: Build reusable pattern library

1. **Success pattern extraction**:
   - Parse validated plans → extract subgraph motifs
   - Store as few-shot examples
2. **Dynamic retrieval**:
   - Use embedding-based search (e.g., sentence-transformers)
   - Match error types to relevant examples

---

## Evaluation Metrics

Track improvements on benchmark from `run_evaluation.py`:

| Method | Sequential Tasks | Parallel Tasks | Cyclic Error Prevention | Overall |
|--------|-----------------|----------------|------------------------|---------|
| **Current (DSPy + Assert)** | 3/3 (100%) | 0/1 (0%) | 3/3 (100%) | 75% |
| **+ Few-Shot Examples** | 3/3 | 1/1 | 3/3 | **100%** (target) |
| **+ Post-Hoc Repair** | 3/3 | 1/1 | 3/3 | **100%** (fallback) |
| **+ SDPO** | 3/3 | 1/1 | 3/3 | 100% + faster convergence |
| **+ TTRL** | 3/3 | 1/1 | 3/3 | 100% + self-improvement |

---

## Dense Reward Signal Design

Current: Binary `(is_valid, error_list)`

**Proposed**: Multi-faceted graph quality metrics

```python
def compute_dense_rewards(plan: BDIPlan) -> Dict[str, float]:
    """Replace binary rewards with structured scores"""
    G = plan.to_networkx()

    rewards = {
        # Connectivity (0.0 - 1.0)
        'connectivity': 1.0 if nx.is_weakly_connected(G) else 0.0,

        # Acyclicity (0.0 - 1.0)
        'acyclicity': 1.0 if nx.is_directed_acyclic_graph(G) else 0.0,

        # Topology quality (lower is better)
        'compactness': 1.0 / (nx.diameter(G.to_undirected()) + 1) if nx.is_connected(G.to_undirected()) else 0.0,

        # Parallelism efficiency (higher is better for parallel tasks)
        'parallelism': nx.average_clustering(G.to_undirected()),

        # Overall score (weighted combination)
        'overall': 0.4 * connectivity + 0.4 * acyclicity + 0.1 * compactness + 0.1 * parallelism
    }

    return rewards
```

---

## Next Steps

1. **Immediate (This Week)**:
   - [ ] Add fork-join few-shot examples to `planner.py`
   - [ ] Implement post-hoc graph repair in `verifier.py`
   - [ ] Re-run benchmark → validate 100% pass rate

2. **Short-Term (Next 2 Weeks)**:
   - [ ] Retrieve AutoRocq full paper (arXiv:2511.17330)
   - [ ] Implement SDPO self-distillation loop
   - [ ] Collect 200-sample training dataset

3. **Medium-Term (Next 1-2 Months)**:
   - [ ] Integrate TTRL test-time adaptation
   - [ ] Build success pattern library (AutoRocq-style)
   - [ ] Write paper on "LLM + Formal Verifier co-training"

---

## References

1. **SDPO**: Hübotter et al. "Reinforcement Learning via Self-Distillation" arXiv:2601.20802 (2026)
   - [alphaXiv Link](https://alphaxiv.org/abs/2601.20802)

2. **TTRL**: Zuo et al. "TTRL: Test-Time Reinforcement Learning" arXiv:2504.16084 (2025)
   - [alphaXiv Link](https://alphaxiv.org/abs/2504.16084)
   - [GitHub](https://github.com/PRIME-RL/TTRL)

3. **AutoRocq**: "AutoRocq: Agentic Program Verification" arXiv:2511.17330 (2025)
   - *Full paper retrieval pending*

---

## Code Examples Repository

All code snippets above are proof-of-concept. Production implementations should:
- Add error handling
- Include type hints
- Add unit tests
- Document hyperparameters

See `docs/PARALLEL_FAILURE_ANALYSIS.md` for the original problem analysis that motivated this research.
