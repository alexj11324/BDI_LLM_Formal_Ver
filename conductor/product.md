# Product Definition

## Project Name

BDI-LLM Formal Verification Framework (PNSV)

## Description

A neuro-symbolic planning framework that combines LLM generation with formal verification to produce provably correct plans. Uses a Pluggable Neuro-Symbolic Verification (PNSV) engine with a 3-layer verification pipeline to catch and repair hallucinated or logically inconsistent LLM-generated plans.

## Problem Statement

LLM-generated plans frequently contain hallucinations, logical inconsistencies, and physically impossible action sequences. There is no reliable way to guarantee the correctness of plans produced by language models without a formal verification layer. Current approaches either blindly trust LLM outputs or require expensive manual review.

## Target Users

1. **AI/ML Researchers** — Studying neuro-symbolic reasoning, automated planning, and LLM reliability
2. **AI Agent Developers** — Building agents that need provably correct plan execution (via MCP integration)
3. **Student Model Trainers** — Using verified "Golden Trajectories" to fine-tune smaller models via R1 distillation

## Key Goals

1. **Provable Correctness** — Ensure every LLM-generated plan satisfies structural, symbolic, and domain-physics constraints before execution
2. **Verification + Repair Closed Loop** — Implement the complete BDI plan-verify-repair cycle: generate plan → 3-layer verification → auto-repair using verifier feedback → re-verify (up to 3 iterations). This is the project's central contribution.
3. **Domain Agnosticity** — Support diverse planning domains (PlanBench: Blocksworld, Logistics, Depots; SWE-bench: software engineering) via a polymorphic verification bus
4. **Dynamic Replanning** — Support runtime re-planning when simulated execution diverges from expected world state (multi-episode plan-execute-replan)
5. **Distillation Pipeline** — Generate high-quality thinking trajectories from successful verify-repair loops for fine-tuning smaller student models
