---
description: Run the full test suite for BDI LLM Formal Verification project
---

# Run Tests Workflow

// turbo-all

1. Activate the Python virtual environment:
```bash
source /Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver/.venv/bin/activate
```

2. Run all pytest tests with verbose output:
```bash
cd /Users/alexjiang/Documents/RA/BDI_LLM_Formal_Ver && python -m pytest tests/ -v --tb=short
```

3. Report any failures and suggest fixes.
