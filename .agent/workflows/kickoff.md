---
description: Start a new project or resume from where you left off - initializes Memory state and runs first iteration
---

# Kickoff: Initialize or Resume

This workflow either starts a new project baseline or resumes from a previous session.

## Step 1: Check for Existing State

Search Memory MCP:
- `memory_search({ query: "iteration-state" })`

**If state exists**: Display the last iteration summary and ask:
> "Found previous state: [summary]. Continue iterating from here?"

**If no state exists**: Proceed to Step 2 to establish baseline.

## Step 2: Establish Baseline (First Time Only)

1. Run `/run-tests` to get current test pass rate
2. Run `/evaluate-planbench` if PlanBench data is available
3. Document the baseline:

```
memory_write({
  key: "iteration-state",
  type: "status",
  content: "Iteration #0 (Baseline): PlanBench pass rate: X%. Test pass rate: Y%. No fixes applied yet.",
  tags: ["iteration", "bdi", "baseline"]
})
```

```
memory_write({
  key: "project-targets",
  type: "config",
  content: "PlanBench target: >99%. SWE-bench target: >90%. Current focus: PlanBench maintenance.",
  tags: ["targets", "bdi", "config"]
})
```

## Step 3: Begin First Iteration

Run `/iterate` to start the first improvement cycle.

## Step 4: Repeat

After each `/iterate` completes, you can:
- Run `/iterate` again for the next cycle
- Run `/kickoff` in a new session to resume from saved state
