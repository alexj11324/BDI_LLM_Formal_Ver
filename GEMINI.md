# Project Context

## Project Goals
- **Core Mission:** A formal verification + auto-repair framework (Pluggable Neuro-Symbolic Verification - PNSV) implementing the complete BDI plan-verify-repair closed loop for LLM-generated plans.
- **Verification + Repair (Complete BDI Loop):** The framework generates LLM plans as IntentionDAGs, verifies them through 3 layers, and **automatically repairs** failed plans using verifier feedback (up to 3 iterations). This mirrors the classical BDI plan-execute-replan cycle advocated by Anand Rao.
- **Target Audience:** The research paper demonstrates that the BDI + 3-layer verification + auto-repair pipeline elevates LLM plan correctness from NAIVE baseline to provably correct outputs, comparing across NAIVE / BDI_ONLY / FULL_VERIFIED / FULL_VERIFIED+REPAIR modes.
- **Evaluation Domains:** PlanBench (Blocksworld, Logistics, Depots) and SWE-bench. Medical domain (sleep disorders) is a future goal pending UPMC data access.

## Technology Stack
- **Languages:** Python (Primary, DSPy)
- **Engine:** BDI Engine logic running against an OpenAI-compatible LLM schema (currently configured for Alibaba Cloud DashScope `qwq-plus` for batch inferences).
- **Validation Layers:** 
  1. Structural Verification (using NetworkX DAG structures)
  2. Symbolic Verification (using PDDL / VAL binary)
  3. Domain Physics Simulation (domain-specific state verification)
- **Repair:** Auto-repair engine using verifier error feedback to iteratively correct invalid plans (`src/bdi_llm/plan_repair.py`).

## Workflow & Guidelines
- **Development Workflow:** Evaluate the complete BDI closed loop — plan generation → 3-layer verification → auto-repair → re-verification. Compare across ablation modes (NAIVE / BDI_ONLY / FULL_VERIFIED / FULL_VERIFIED+REPAIR).
- **Testing:** Run test sets across Blocksworld, Logistics, and Depots domains using `scripts/evaluation/run_planbench_full.py` with `--execution_mode FULL_VERIFIED`. Also use `scripts/evaluation/run_verification_only.py` for verification-only baselines and `scripts/replanning/run_dynamic_replanning.py` for the replanning pipeline.
- **API Use:** All Batch inference configurations must use the `DASHSCOPE_API_KEY`.
- **Note:** Never run actions without an explicit, verifiable objective to avoid unintended side effects. Keep logic simple, strictly verified.

