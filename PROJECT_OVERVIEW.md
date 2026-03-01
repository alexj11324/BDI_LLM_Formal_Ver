# BDI-LLM: Neuro-Symbolic Planning with Formal Verification

## Overview

BDI-LLM is a research framework that combines Large Language Models with formal verification to generate provably correct planning solutions. The system bridges neural generation and symbolic reasoning by subjecting LLM-generated plans to rigorous multi-layer verification.

## Core Architecture

```
Natural Language Problem → LLM Plan Generation → Multi-Layer Verification → Verified PDDL Plan
                              (DSPy)              (Structural + VAL + Physics)
```

### Key Components

1. **PDDL-to-NL Translation**: Converts formal planning problems into structured natural language with the BDI (Belief-Desire-Intention) model.
2. **Structured Plan Generation**: Uses DSPy signatures to generate plans as directed graphs.
3. **Three-Layer Verification**:
   - Layer 1: Structural verification (DAG validity, connectivity)
   - Layer 2: Symbolic verification (VAL validator for PDDL correctness)
   - Layer 3: Domain-specific physics validation
4. **Error-Driven Repair**: Iterative repair loop using verifier diagnostics to guide plan fixes.

## Repository Structure (Reorganized)

```
├── src/bdi_llm/                        # Core framework implementation
├── scripts/                            # Evaluation, benchmark, and utility entrypoints
├── tests/                              # Pytest test suite
├── docs/                               # User/system/provenance/organization docs
├── planbench_data/                     # PlanBench dataset and planner/VAL tooling
├── runs/                               # Mutable experiment outputs
│   ├── planbench_*.json/png            # Non-canonical summaries/charts
│   └── legacy/                         # Historical pre-freeze outputs
├── artifacts/paper_eval_20260213/      # Frozen, canonical paper evidence snapshot
├── BDI_Paper/                          # Paper source files
├── README.md / README_CN.md            # Primary entry documentation
└── requirements.txt                    # Runtime dependencies
```

## Supported Domains

- **Blocksworld**: Block stacking and manipulation
- **Logistics**: Multi-city package delivery with trucks and airplanes
- **Depots**: Warehouse operations with hoists and trucks

## Getting Started

- User guide: `docs/USER_GUIDE.md`
- Architecture: `docs/ARCHITECTURE.md`
- Benchmark notes: `docs/BENCHMARKS.md`
- Provenance and frozen evidence: `docs/PAPER_RESULT_PROVENANCE.md`
- Repository boundaries and mutability: `docs/REPO_ORGANIZATION.md`

## License

MIT License. See `LICENSE`.
