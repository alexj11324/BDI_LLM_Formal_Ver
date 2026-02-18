---
description: Evaluate the BDI planner against PlanBench domains and report success rate
---

# Evaluate PlanBench Workflow

1. Check that the VAL binary is available at `planbench_data/planner_tools/VAL/validate`.
2. Run the evaluation script against the target domain:
```bash
# Evaluate Blocksworld with 400 workers for max throughput
python scripts/run_planbench_full.py --domain blocksworld --parallel --workers 400
```
3. Collect success/failure counts and compute the pass rate.
4. If pass rate < 99%, identify failing instances and analyze error patterns.
5. Suggest prompt or planner fixes to improve the pass rate.
