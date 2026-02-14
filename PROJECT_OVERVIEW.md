# BDI-LLM: Neuro-Symbolic Planning with Formal Verification

## Overview

BDI-LLM is a research framework that combines Large Language Models with formal verification to generate provably correct planning solutions. The system bridges the gap between neural generation and symbolic reasoning by subjecting LLM-generated plans to rigorous multi-layer verification.

## Core Architecture

```
Natural Language Problem → LLM Plan Generation → Multi-Layer Verification → Verified PDDL Plan
                              (DSPy)              (Structural + VAL + Physics)
```

### Key Components

1. **PDDL-to-NL Translation**: Converts formal planning problems into structured natural language using the BDI (Belief-Desire-Intention) model
2. **Structured Plan Generation**: Uses DSPy framework with domain-specific signatures to generate plans as directed acyclic graphs
3. **Three-Layer Verification**:
   - Layer 1: Structural verification (DAG validity, connectivity)
   - Layer 2: Symbolic verification (VAL validator for PDDL correctness)
   - Layer 3: Domain-specific physics validation
4. **Error-Driven Repair**: Iterative repair loop using VAL diagnostics to guide LLM corrections

## Repository Structure

```
├── src/bdi_llm/          # Core framework implementation
├── scripts/              # Evaluation and demo scripts
├── tests/                # Unit and integration tests
├── docs/                 # Architecture and user documentation
├── planbench_data/       # PlanBench benchmark dataset
└── results/              # Benchmark results and visualizations
```

## Supported Domains

- **Blocksworld**: Block stacking and manipulation
- **Logistics**: Multi-city package delivery with trucks and airplanes
- **Depots**: Warehouse operations with hoists and trucks

## Key Results

- **High Accuracy**: Achieves competitive performance on PlanBench benchmark
- **Formal Guarantees**: All generated plans are VAL-verified for correctness
- **Effective Repair**: 96.4% repair success rate when initial plans fail verification

## Getting Started

See [USER_GUIDE.md](docs/USER_GUIDE.md) for installation and usage instructions.

## Experiment Data

Historical experiment results are archived in `planbench_results_archive.tar.gz` (2.6MB).

## License

MIT License - See [LICENSE](LICENSE) for details.
