# Standard Planning Benchmarks vs. Current BDI-LLM Setup

**Date**: 2026-02-03
**Status**: Research for benchmark expansion

---

## 📊 Your Current Benchmark (Honest Assessment)

### Current Setup
- **Size**: 4 scenarios
- **Type**: Hand-crafted BDI planning tasks
- **Coverage**:
  - ✅ Sequential planning (simple_navigation, locked_door)
  - ✅ Complex multi-step (complex_preparation)
  - ❌ **Parallel tasks** (parallel_tasks) ← Current failure point
- **Validation**: NetworkX DAG verifier (structural only)

### Reality Check
**You're absolutely right** - 4 scenarios is NOT a standard benchmark for publication. This is more of a "proof-of-concept" test suite.

---

## 🏆 What SOTA Papers Actually Use

### 1. TTRL (Test-Time RL) - Mathematical Reasoning

| Dataset | Size | Task Type | Metric |
|---------|------|-----------|--------|
| **AIME 2024** | 30 problems | High school math competition | pass@1 accuracy |
| **AMC** | ~25 problems | Math competition | pass@1, Maj@N |
| **MATH-500** | 500 problems | Mathematical reasoning | pass@1, Avg@64 |

**Total evaluation scale**: ~555 problems

**Performance**: 12.9% → 40.2% (211% improvement)

---

### 2. SDPO (Self-Distillation) - Code Generation

| Dataset | Size | Task Type | Metric |
|---------|------|-----------|--------|
| **LiveCodeBench v6** | 28 "hard" tasks analyzed | Competitive programming | pass@64, execution success |
| **LiveCodeBench v6 (full)** | 400+ total problems | Real competition problems | pass@k |
| **IFEval** | Undisclosed | Instruction following | Format compliance |
| **ArenaHard-v2** | Undisclosed | Real-world prompts | LLM-as-judge |
| **MMLU-Pro** | Undisclosed | Multi-task knowledge | Accuracy |

**Total evaluation scale**: 400+ problems (code alone)

**Performance**: Significant improvements on hard problems (pass@64 < 0.03)

---

### 3. SWE-Universe - Software Engineering

**From the paper (arXiv:2602.02361)**:

| Feature | Scale |
|---------|-------|
| **Source** | GitHub Pull Requests |
| **Automatic Generation** | Scalable to **millions** of environments |
| **Verification** | Unit test execution (automatic oracle) |
| **Domains** | Real-world software projects |

**Key Innovation**: Auto-generates verifiable environments from open-source PRs

**Comparison to SWE-bench**: Scales orders of magnitude larger

---

## 📚 Standard Planning Benchmarks (Classical AI)

### IPC (International Planning Competition)

| Domain | # Problems | Complexity |
|--------|-----------|------------|
| **Blocksworld** | 100+ | Classic stacking |
| **Logistics** | 50+ | Multi-city transport |
| **Rovers** | 40+ | Mars exploration |
| **Satellite** | 36+ | Communication planning |
| **Gripper** | 20+ | Robot manipulation |
| **Zenotravel** | 20+ | Travel planning |
| **+ 50-80 more domains** | **2000-5000+ total** | Various |

**Repository**: [planning.domains](http://planning.domains)

**Format**: PDDL (Planning Domain Definition Language)

**Metrics**:
- Plan validity (goal achievement)
- Plan optimality (shortest path)
- Planning time
- Memory usage

---

### Planning.domains Repository

**Scale**:
- **50-80+ domains** (planning scenarios)
- **Thousands of problem instances**
- **Spans IPC 1998-2024**

**Access**:
- Website: http://planning.domains
- GitHub: https://github.com/AI-Planning/pddl-generators

---

## 🤖 LLM Planning Benchmarks (2024-2025)

### AgentBench
- **Size**: Multi-environment suite
- **Tasks**: Web browsing, database queries, OS interaction
- **Models Tested**: GPT-4, Claude-3, Llama, etc.
- **Metrics**: Task success rate, efficiency

### PlanBench
- **Focus**: Classical planning with LLMs
- **Tasks**: PDDL-based problems
- **Evaluation**: Plan correctness, PDDL syntax validity

### WebArena
- **Size**: Realistic website interaction scenarios
- **Tasks**: Long-horizon web navigation
- **Metrics**: Goal completion rate

### SWE-bench (Original)
- **Size**: 2,294 GitHub issues
- **Source**: 12 popular Python repos
- **Verification**: Unit test execution
- **SOTA**: ~13% resolution rate (GPT-4)

---

## 💡 Recommended Benchmark Strategy for BDI-LLM

### Phase 1: Expand to Standard Size (Target: 50-100 scenarios)

#### Option A: BDI-Specific Domains (Recommended)
```python
# Household Robot Tasks (20 scenarios)
- Kitchen tasks (cooking, cleaning)
- Navigation with obstacles
- Multi-room coordination
- Object manipulation

# Office Automation (15 scenarios)
- Email + calendar management
- Document processing pipelines
- Meeting room scheduling
- Resource allocation

# Smart Home (15 scenarios)
- Energy optimization
- Security protocols
- Comfort management
- Emergency response
```

**Advantages**:
- Domain-aligned with BDI literature
- Clear goal-oriented tasks
- Easy to define beliefs/desires
- Verifiable outcomes

#### Option B: Adapt IPC Benchmarks
```python
# Convert PDDL to BDI format
from pddl_parser import parse_pddl_domain

def pddl_to_bdi(pddl_problem):
    beliefs = extract_initial_state(pddl_problem)
    desire = extract_goal_state(pddl_problem)
    # LLM generates BDIPlan
    return (beliefs, desire)
```

**Advantages**:
- Large existing corpus (2000+ problems)
- Well-established baselines
- Community recognition

**Disadvantages**:
- Requires PDDL → BDI translation
- May not showcase LLM strengths

### Phase 2: Add Real-World Tasks (Target: 100-500 scenarios)

#### GitHub Issue Resolution (SWE-Universe Style)
```python
# For each GitHub PR:
beliefs = """
- Codebase structure: {repo_structure}
- Current bug: {issue_description}
- Test failures: {failing_tests}
"""

desire = "Fix the bug and pass all tests"

# Verifier: Run test suite
is_valid = run_tests(generated_plan)
```

**Scale**: Potentially millions (auto-generated)

#### Embodied AI Tasks
- ALFWorld scenarios (130+ interactive tasks)
- VirtualHome (1000+ household activities)
- ALFRED (25,743 task instances)

---

## 📈 Metrics to Track (Beyond DAG Validity)

### Structural Metrics (Current)
- ✅ DAG validity (no cycles)
- ✅ Connectivity (weakly connected)
- ✅ Topological sort (execution order)

### Additional Metrics to Add

#### Planning Quality
```python
def evaluate_plan_quality(plan, gold_standard):
    return {
        'optimality': len(plan.nodes) / len(gold_standard.nodes),
        'redundancy': count_unnecessary_actions(plan),
        'coverage': goal_achievement_score(plan),
        'efficiency': execution_time(plan)
    }
```

#### Generalization
```python
def test_generalization():
    """Test on held-out scenarios"""
    train_domains = ['kitchen', 'office']
    test_domains = ['warehouse', 'hospital']  # New!

    return cross_domain_accuracy(test_domains)
```

#### Robustness
```python
def test_robustness():
    """Adversarial/edge cases"""
    return {
        'noisy_beliefs': accuracy_with_wrong_info(),
        'ambiguous_goals': handles_unclear_desires(),
        'dynamic_environment': adapts_to_changes()
    }
```

---

## 🎯 Concrete Recommendations for Your Project

### Immediate (This Week)
1. **Fix parallel task bug** with auto-repair → 4/4 (100%)
2. **Document current 4-scenario benchmark** as "initial validation"

### Short-term (2-4 weeks)
1. **Expand to 20-30 scenarios**:
   - 10 household robot tasks
   - 10 office automation tasks
   - 5 edge cases (parallel, long-horizon, ambiguous)

2. **Add semantic evaluation**:
   - LLM-as-judge for goal achievement
   - Human evaluation on subset (5-10 examples)

### Medium-term (1-2 months)
1. **Convert 50-100 IPC problems**:
   - Blocksworld (10 problems)
   - Logistics (10 problems)
   - Rovers (10 problems)
   - Custom BDI domains (20 problems)

2. **Implement additional metrics**:
   - Plan optimality scoring
   - Generalization testing
   - Robustness evaluation

### Long-term (3-6 months, for publication)
1. **Large-scale benchmark** (100-500 scenarios):
   - IPC-derived problems (100)
   - BDI-specific tasks (100)
   - Real-world GitHub issues (100-300)

2. **Comparative baselines**:
   - GPT-4 (direct prompting)
   - Claude Opus 4 (direct prompting)
   - Fine-tuned models (if applicable)
   - Classical planners (for IPC problems)

3. **Ablation studies**:
   - LLM only (no verifier)
   - Verifier only (no LLM self-correction)
   - Full pipeline (current)
   - +SDPO training
   - +TTRL test-time adaptation

---

## 📝 Benchmark Comparison Table

| Benchmark | Size | Domain | Your Project Fit |
|-----------|------|--------|------------------|
| **Your current** | 4 | BDI planning | ✅ Proof of concept |
| **IPC (full)** | 2000-5000 | Classical planning | 🟨 Need PDDL conversion |
| **AIME/MATH** | 500+ | Math reasoning | ❌ Different task type |
| **LiveCodeBench** | 400+ | Code generation | 🟨 Could adapt (code planning) |
| **SWE-bench** | 2,294 | Software engineering | 🟨 Could adapt (issue resolution) |
| **SWE-Universe** | Millions | Software engineering | ✅ Auto-generation strategy! |
| **ALFWorld** | 130+ | Embodied AI | ✅ Good BDI fit |
| **WebArena** | Dozens | Web interaction | 🟨 Multi-step planning |

### Best Strategy for Your Project

**Recommendation**: **SWE-Universe-inspired approach + IPC subset**

```python
# 1. Auto-generate BDI tasks from structured sources
def generate_bdi_benchmark():
    # From GitHub (SWE-Universe style)
    github_tasks = extract_issues_as_bdi(popular_repos, limit=100)

    # From IPC (classical planning)
    ipc_tasks = convert_pddl_to_bdi(ipc_domains, limit=100)

    # Custom BDI scenarios
    custom_tasks = load_handcrafted_scenarios(limit=50)

    return github_tasks + ipc_tasks + custom_tasks  # 250 scenarios

# 2. Automatic verification
def verify_task(task, plan):
    if task.source == 'github':
        return run_unit_tests(plan)
    elif task.source == 'ipc':
        return pddl_validator(plan)
    else:
        return dag_verifier(plan) + semantic_check(plan)
```

**Advantages**:
- **Scalable**: Can auto-generate 100s-1000s of tasks
- **Verifiable**: Automatic oracles (test execution, PDDL validation)
- **Diverse**: Covers real-world + classical planning
- **Novel**: First to combine BDI + LLM + DAG verification at scale

---

## ⚠️ Critical Insight

**Your 4-scenario benchmark is NOT publication-ready as-is**, but your **verification methodology** is publication-worthy!

The innovation isn't the benchmark size - it's the **formal verification + self-correction loop**:

```
LLM Generation → DAG Verifier → Self-Correction (DSPy Assert)
                      ↓
                Error Feedback (SDPO-style)
                      ↓
                Dense Rewards (TTRL-style)
```

**Strategy**:
1. **Quick Fix**: Expand to 20-30 scenarios (sufficient for workshop/arxiv)
2. **Medium**: 50-100 scenarios (sufficient for conference)
3. **Long**: 100-500 scenarios (sufficient for top-tier venue)

But **don't wait** - your current 4-scenario setup is enough to:
- ✅ Validate the core method works
- ✅ Demonstrate SDPO/TTRL integration
- ✅ Publish as "preliminary results" or "proof of concept"
- ✅ Release open-source tool for community to extend

**The verifier is the key - not the benchmark size!** 🔑

---

## 📚 References

- IPC Benchmarks: http://planning.domains
- SWE-bench: https://www.swebench.com
- ALFWorld: https://alfworld.github.io
- PDDL Generators: https://github.com/AI-Planning/pddl-generators
- SWE-Universe: arXiv:2602.02361

Your next commit should expand the benchmark to 20-30 scenarios. That's the minimum viable size for serious evaluation. 🎯
