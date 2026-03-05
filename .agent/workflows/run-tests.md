---
description: Run the full test suite for BDI LLM Formal Verification project
---

# Run Tests Workflow

// turbo-all

1. Activate the Python virtual environment:
```bash
source .venv/bin/activate
```

2. Run all pytest tests with verbose output:
```bash
python -m pytest tests/ -v --tb=short
```

3. Report any failures and suggest fixes.
