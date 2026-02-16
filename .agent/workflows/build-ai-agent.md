---
description: Build a production-grade AI agent system with measurable reliability, following the 4-step framework
---

# Build an AI Agent System

Design and deliver a production-grade agent with measurable reliability.

## Step 1: Define Target Behavior and KPIs

- **Goal:** Set quality, latency, and failure thresholds.
- **Skills:** `@ai-agents-architect`, `@agent-evaluation`, `@brainstorming`
- Define success criteria (e.g., >90% SWE-bench, >99% PlanBench)
- Identify failure modes and edge cases
- Establish baseline metrics

## Step 2: Design Retrieval and Memory

- **Goal:** Build reliable retrieval and context architecture.
- **Skills:** `@agent-memory-systems`, `@agent-memory-mcp`
- Design how the agent stores and retrieves past experiences
- Choose chunking, embedding, and retrieval strategies
- Implement context window management

## Step 3: Implement Orchestration

- **Goal:** Implement deterministic orchestration and tool boundaries.
- **Skills:** `@agent-tool-builder`, `@async-python-patterns`
- Wire up MCP tools (e.g., `generate_verified_plan`)
- Implement the BDI plan-verify-execute loop
- Add fallback and human-in-the-loop mechanisms

## Step 4: Evaluate and Iterate

- **Goal:** Improve weak points with a structured loop.
- **Skills:** `@agent-evaluation`, `@agent-orchestration-improve-agent`
- Run benchmarks (PlanBench, SWE-bench)
- Identify failure patterns and root causes
- Optimize prompts, repair logic, and tool descriptions
- Re-evaluate until targets are met
