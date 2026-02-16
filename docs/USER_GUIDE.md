
# Integration Guide: Multi-Layer Symbolic Verification & Coding Domain

**Last Updated**: 2026-02-16
**Purpose**: Guide for using the verification system and the new Coding Domain agent.

---

## Overview

The BDI-LLM framework now supports two primary domains:
1.  **Planning Domain**: Blocksworld/Logistics planning with multi-layer verification (Structural, Symbolic, Physics).
2.  **Coding Domain**: Software engineering agent for fixing GitHub issues (SWE-bench).

---

## Part 1: Planning Domain (PlanBench)

### Quick Start

```bash
# Run full 100-instance benchmark
python scripts/run_planbench_full.py --domain blocksworld --max_instances 100 --parallel --workers 50
```

### Verification Layers
1. **Layer 1 - Structural**: DAG properties (cycles, connectivity).
2. **Layer 2a - Physics**: Domain-specific constraints (Blocksworld).
3. **Layer 2b - Symbolic**: PDDL semantic validation (VAL).

(See `docs/ARCHITECTURE.md` for details)

---

## Part 2: Coding Domain (New)

The Coding Domain allows the BDI agent to solve software engineering tasks by reading, editing, and testing code in a local environment.

### Features
- **Local Harness**: Runs SWE-bench instances locally without Docker (for rapid dev).
- **Iterative Fix**: "Plan -> Edit -> Verify" loop.
- **Fail-Fast**: Stops immediately if critical steps fail.

### Usage

#### 1. Run the Iterative Fix Loop
To attempt a fix on a specific SWE-bench instance (e.g., `astropy__astropy-12907`):

```bash
python scripts/run_iterative_fix.py --instances astropy__astropy-12907
```

#### 2. Run on Multiple Instances
To run on the first N instances from the SWE-bench Verified dataset:

```bash
python scripts/run_iterative_fix.py --limit 5
```

### How it Works
1.  **Setup**: Clones the repository and checks out the base commit.
2.  **Plan**: BDI Planner generates a DAG of actions (`read-file`, `edit-file`, `run-test`).
3.  **Execute**:
    - `read-file`: Reads file content.
    - `edit-file`: LLM generates a patch based on the issue description.
    - `run-test`: Runs local tests to verify the fix.
4.  **Report**: Outputs changed files and execution status.

### Configuration
The harness stores repos in `swe_bench_workspace/`. You can clean this directory to reset state.

---

## Troubleshooting

### Planning Domain
- **VAL Errors**: Ensure VAL binaries are in `planbench_data/val_binaries/`.
- **API Errors**: Check `OPENAI_API_KEY` or Vertex AI config in `.env`.

### Coding Domain
- **Missing Dependencies**: Ensure you have installed requirements (`pip install -r requirements.txt`).
- **Test Failures**: Local environment must match the repo's requirements. Some older SWE-bench instances may strictly require Docker.

---

## References
- **Benchmarks**: `docs/BENCHMARKS.md`
- **Architecture**: `docs/ARCHITECTURE.md`
- **Code**: `src/bdi_llm/coding_planner.py`, `scripts/swe_bench_harness.py`
