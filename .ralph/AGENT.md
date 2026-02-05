# Ralph Agent Configuration

## Build Instructions

```bash
# No build step needed - Python project
# Dependencies installed via: pip install -r requirements.txt
```

## Test Instructions

```bash
# Run verifier tests (no API key needed)
pytest tests/test_verifier.py -v

# Run symbolic verifier tests
pytest tests/test_symbolic_verifier.py -v

# Run integration tests (requires API key)
pytest tests/test_integration.py -v

# Run all tests
pytest tests/ -v
```

## Run Instructions

```bash
# Unit tests only (no API key required)
python run_evaluation.py --mode unit

# Offline demo (no API key, shows verifier capabilities)
python run_evaluation.py --mode demo-offline

# Full LLM integration test (requires API key)
python run_evaluation.py --mode demo

# PlanBench evaluation (3 instances for quick testing)
python run_planbench_full.py --domain blocksworld --max_instances 3

# Full 100-instance benchmark
python run_planbench_full.py --domain blocksworld --max_instances 100
```

## Notes
- API Key: Set OPENAI_API_KEY for CMU AI Gateway (Claude Opus 4)
- Platform: macOS compatible for Layer 2a (BlocksworldPhysicsValidator)
- VAL verifier (Layer 2b): Linux only - DO NOT use PDDLSymbolicVerifier on macOS
- See docs/ALLOWED_APIS_REFERENCE.md for verified API patterns (Phase 0 complete)

