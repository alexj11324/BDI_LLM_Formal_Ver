---
description: Run one full improvement iteration - evaluate, analyze failures, fix, re-evaluate, and save state for next session
---

# Iterate: One Improvement Cycle

This workflow runs one complete improvement cycle. Each cycle is self-contained
and persists its results so the next session can continue where this one left off.

## Step 1: Load Previous State

Search Memory MCP for the latest iteration state:
- `memory_search({ query: "iteration-state" })`
- `memory_search({ query: "failure-patterns" })`

If no previous state exists, this is iteration #1. Establish baseline.

## Step 2: Run Evaluation

Execute the appropriate benchmark:
- For PlanBench: Run `/evaluate-planbench`
- For coding tasks: Run tests with `/run-tests`

Record the results:
- Total test count
- Pass count and pass rate
- List of failing test names

## Step 3: Analyze Failures

For each failing test:
1. Identify the failure category (planning error, verification error, domain gap, prompt issue)
2. Rank failures by frequency and impact
3. Pick the top 1-3 most impactful failures to fix this iteration

Do NOT try to fix everything at once. Focus on highest-impact fixes.

## Step 4: Implement Fix

Based on the analysis:
- **Prompt issue** → Edit DSPy signatures in `src/bdi_llm/planner.py`
- **Verification error** → Fix `src/bdi_llm/symbolic_verifier.py`
- **Domain gap** → Update PDDL domain files in `planbench_data/`
- **Tool description** → Improve `src/mcp_server_bdi.py` tool schema

Make the minimal change needed. Run `/run-tests` after each fix to verify no regressions.

## Step 5: Re-Evaluate

Run the same benchmark again from Step 2.
Compare new results vs previous results.

## Step 6: Save Iteration State

Write to Memory MCP for next session:

```
memory_write({
  key: "iteration-state",
  type: "status",
  content: "Iteration #N: Pass rate X% → Y%. Fixed: [description]. Remaining failures: [list]. Next target: [goal].",
  tags: ["iteration", "bdi", "evaluation"]
})
```

If new failure patterns were identified:
```
memory_write({
  key: "failure-patterns",
  type: "analysis",
  content: "Top failure patterns: 1) ... 2) ... 3) ...",
  tags: ["failures", "bdi", "analysis"]
})
```

## Step 7: Summary

Present a brief iteration report:
- ✅ What improved
- ❌ What still fails
- 🎯 Recommended focus for next `/iterate`
