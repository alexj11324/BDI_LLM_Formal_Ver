# PRD: BDI_LLM_Formal_Ver 仓库全面治理

## Overview

对 `/Users/alexjiang/Desktop/BDI_LLM_Formal_Ver` 仓库执行全面治理，包括目录重组（Phase 2）和代码重构（Phase 3）。

**安全备份**: 已在 `backup/pre-reorg-20260305` 分支。

**完整计划**: 见 `~/.gemini/antigravity/brain/f220e873-61a4-4c4a-aab9-57b51c8952e5/organize_repo_full_plan.md`

**关键约束**:
- 每个 Task 完成后必须 `git commit -m "reorg: <task描述>"`
- Phase 2 和 Phase 3 不可并行
- 所有 Git 跟踪文件用 `git mv`，未跟踪文件用 `mv`
- 遇到 `git rm` 目标不存在时用 `|| true` 跳过
- 每个 Phase 3 Target 完成后运行 `pytest tests/ -v --tb=short` 验证

---

## Task 1: Batch 1 — 清理数据和临时文件

从 Git 移除数据文件（保留磁盘），清理无用文件和空目录。

```bash
cd /Users/alexjiang/Desktop/BDI_LLM_Formal_Ver

# 1. 实验数据
git rm -r --cached swe_bench_workspace/ 2>/dev/null || true
git rm -r --cached swe_bench_workspace_recheck/ 2>/dev/null || true
git rm -r --cached swe_bench_workspace_recheck2/ 2>/dev/null || true
git rm -r --cached swe_bench_workspace_recheck3/ 2>/dev/null || true
git rm -r --cached swe_bench_workspace_recheck4/ 2>/dev/null || true
git rm -r --cached swe_bench_workspace_recheck5/ 2>/dev/null || true
git rm -r --cached swe_bench_workspace_recheck_requests/ 2>/dev/null || true
git rm -r --cached runs/ 2>/dev/null || true
git rm -r --cached mlruns/ 2>/dev/null || true

# 2. 本地产物
git rm --cached .DS_Store 2>/dev/null || true
git rm --cached mlflow.db 2>/dev/null || true

# 3. 私密数据
git rm --cached "RA 第二次_原文.txt" 2>/dev/null || true
git rm --cached "RA第一次会议.txt" 2>/dev/null || true

# 4. 已删除但未提交的文件
git rm PR21_FIXES.md PROJECT_OVERVIEW.md progress.txt prompt.md task_spec.md 2>/dev/null || true
git rm tasks/PRD-tasks-1772477038161.md tasks/PRD-tasks-1772477138860.md 2>/dev/null || true
git rm docs/ARCHITECTURE.md docs/RESEARCH_TEAM_REPORT.md docs/STRUCTURAL_VERIFICATION_REDESIGN.md 2>/dev/null || true

# 5. 杂项
git rm --cached firebase-debug.log 2>/dev/null || true
git rm --cached jules_awaiting.txt 2>/dev/null || true
git rm --cached demo_mcp_client.py 2>/dev/null || true
git rm --cached STATE_SUMMARY.md 2>/dev/null || true
git rm --cached "tests/test_mcp_server.py.bak" 2>/dev/null || true
git rm --cached "tests/test_plan_repair 2.py" 2>/dev/null || true

# 6. 空目录
rm -rf BDI_LLM_Formal_Ver/ 2>/dev/null || true
rm -rf prd/ 2>/dev/null || true
rm -rf swe_bench_data/ 2>/dev/null || true
rm -rf swe_bench_workspace_dryrun/ 2>/dev/null || true
rm -rf tmp_ws/ tmp_ws2/ 2>/dev/null || true
rm -rf reports/ 2>/dev/null || true

git commit -m "reorg: batch1 - remove tracked data, temp, and private files"
```

**验证**: `git status` 不应再显示数据文件夹。

---

## Task 2: Batch 2 — 更新 .gitignore

追加新的 ignore 规则到 .gitignore。

```bash
cd /Users/alexjiang/Desktop/BDI_LLM_Formal_Ver

cat >> .gitignore << 'EOF'

# === Reorg additions (2026-03-05) ===

# Experiment data (use DVC or external storage)
swe_bench_workspace*/
planbench_data/
runs/
mlruns/
mlflow.db

# Generated outputs
artifacts/
reports/
exports/
tmp_ws*/

# Local artifacts
firebase-debug.log
*.db

# Private meeting transcripts
RA*.txt
EOF

git add .gitignore
git commit -m "reorg: batch2 - update .gitignore with data/artifact exclusions"
```

---

## Task 3: Batch 3 — 文档整合

将散落的文档整合到 `docs/` 下。

```bash
cd /Users/alexjiang/Desktop/BDI_LLM_Formal_Ver

# C4 文档
mkdir -p docs/c4
git mv C4-Documentation/c4-context.md docs/c4/ 2>/dev/null || true
git mv C4-Documentation/c4-container.md docs/c4/ 2>/dev/null || true
git mv C4-Documentation/c4-component.md docs/c4/ 2>/dev/null || true
git mv C4-Documentation/c4-components-detail.md docs/c4/ 2>/dev/null || true
rmdir C4-Documentation 2>/dev/null || true

# Conductor 文档
mkdir -p docs/conductor
git mv conductor/index.md docs/conductor/ 2>/dev/null || true
git mv conductor/product.md docs/conductor/ 2>/dev/null || true
git mv conductor/product-guidelines.md docs/conductor/ 2>/dev/null || true
git mv conductor/tech-stack.md docs/conductor/ 2>/dev/null || true
git mv conductor/tracks.md docs/conductor/ 2>/dev/null || true
git mv conductor/workflow.md docs/conductor/ 2>/dev/null || true

# 配置文件
mkdir -p configs/code_styleguides
git mv conductor/code_styleguides/python.md configs/code_styleguides/ 2>/dev/null || true
git mv conductor/setup_state.json configs/ 2>/dev/null || true
rm -rf conductor 2>/dev/null || true

# PRD 文档
mkdir -p docs/prd
git mv PRD.md docs/prd/ 2>/dev/null || true

# 归档整合
mkdir -p docs/archive/phase1
git mv phase1_archive/* docs/archive/phase1/ 2>/dev/null || true
git mv docs/archive_phase1/* docs/archive/phase1/ 2>/dev/null || true
rmdir phase1_archive 2>/dev/null || true
rmdir docs/archive_phase1 2>/dev/null || true

# wiki-catalogue 到 docs
git mv wiki-catalogue.md docs/ 2>/dev/null || true

git commit -m "reorg: batch3 - consolidate docs (C4, conductor, PRD, archive)"
```

---

## Task 4: Batch 4 — scripts/ 内部重组

按功能分类重组 scripts/ 目录。

```bash
cd /Users/alexjiang/Desktop/BDI_LLM_Formal_Ver

# 创建子目录
mkdir -p scripts/evaluation scripts/batch scripts/replanning scripts/swe_bench scripts/paper

# 评估脚本
git mv scripts/run_planbench_full.py scripts/evaluation/ 2>/dev/null || true
git mv scripts/run_planbench_eval.py scripts/evaluation/ 2>/dev/null || true
git mv scripts/run_planbench_comparison.py scripts/evaluation/ 2>/dev/null || true
git mv scripts/run_verification_only.py scripts/evaluation/ 2>/dev/null || true
git mv scripts/run_evaluation.py scripts/evaluation/ 2>/dev/null || true
git mv scripts/run_glm5_planbench_50_eval.py scripts/evaluation/ 2>/dev/null || true
git mv scripts/verify_paper_eval_snapshot.py scripts/evaluation/ 2>/dev/null || true
git mv scripts/run_stress_test.py scripts/evaluation/ 2>/dev/null || true

# 批量推理
git mv scripts/prepare_batch_jsonl.py scripts/batch/ 2>/dev/null || true
git mv scripts/submit_batch.py scripts/batch/ 2>/dev/null || true
git mv scripts/parse_batch_results.py scripts/batch/ 2>/dev/null || true
git mv scripts/launch_background.py scripts/batch/ 2>/dev/null || true
git mv scripts/launch_sequential.py scripts/batch/ 2>/dev/null || true

# 重规划
git mv scripts/run_dynamic_replanning.py scripts/replanning/ 2>/dev/null || true
git mv scripts/run_batch_replanning.py scripts/replanning/ 2>/dev/null || true

# SWE-bench
git mv scripts/swe_bench_harness.py scripts/swe_bench/ 2>/dev/null || true
git mv scripts/run_swe_bench_batch.py scripts/swe_bench/ 2>/dev/null || true

# 论文图表
git mv scripts/gen_fig2_main_results.py scripts/paper/ 2>/dev/null || true
git mv scripts/gen_fig3_complexity_analysis.py scripts/paper/ 2>/dev/null || true
git mv scripts/gen_fig4_val_repair.py scripts/paper/ 2>/dev/null || true
git mv scripts/gen_fig5_logistics_improvement.py scripts/paper/ 2>/dev/null || true
git mv scripts/gen_results_chart.py scripts/paper/ 2>/dev/null || true

# API test 探针脚本 → 归档
mkdir -p docs/archive/api_probes
git mv scripts/test_chat_completions.py docs/archive/api_probes/ 2>/dev/null || true
git mv scripts/test_configure_dspy.py docs/archive/api_probes/ 2>/dev/null || true
git mv scripts/test_gptoss_config.py docs/archive/api_probes/ 2>/dev/null || true
git mv scripts/test_gptoss_reasoning.py docs/archive/api_probes/ 2>/dev/null || true
git mv scripts/test_gptoss_simple.py docs/archive/api_probes/ 2>/dev/null || true
git mv scripts/test_nvidia_api.py docs/archive/api_probes/ 2>/dev/null || true
git mv scripts/test_nvidia_planner.py docs/archive/api_probes/ 2>/dev/null || true
git mv scripts/test_puter_api.py docs/archive/api_probes/ 2>/dev/null || true
git mv scripts/test_responses_api.py docs/archive/api_probes/ 2>/dev/null || true

# 杂项脚本 → 归档
git mv scripts/quick_fix_parallel_tasks.py docs/archive/ 2>/dev/null || true
git mv scripts/strip_timeouts.py docs/archive/ 2>/dev/null || true
git mv scripts/run_iterative_fix.py docs/archive/ 2>/dev/null || true
git mv scripts/add_symbolic_verification.py docs/archive/ 2>/dev/null || true
git mv scripts/debug_verification_flow.py docs/archive/ 2>/dev/null || true
git mv scripts/run_scientist_team.py docs/archive/ 2>/dev/null || true
git mv scripts/spawn_tmux_research_team.sh docs/archive/ 2>/dev/null || true
git mv scripts/start_planbench_eval.sh docs/archive/ 2>/dev/null || true

git commit -m "reorg: batch4 - restructure scripts/ into evaluation/batch/replanning/paper"
```

---

## Task 5: Batch 5+6 — src/ 和 tests/ 清理

清理 src/ 根散落文件 + 重组 tests/ 目录。

```bash
cd /Users/alexjiang/Desktop/BDI_LLM_Formal_Ver

# --- src/ 清理 ---
git mv src/mcp_server.py docs/archive/ 2>/dev/null || true
git mv src/mcp_server_bdi.py docs/archive/ 2>/dev/null || true
git mv src/sandbox.py docs/archive/ 2>/dev/null || true

# --- tests/ 重组 ---
mkdir -p tests/unit tests/integration tests/smoke

# 单元测试
git mv tests/test_verifier.py tests/unit/ 2>/dev/null || true
git mv tests/test_symbolic_verifier.py tests/unit/ 2>/dev/null || true
git mv tests/test_plan_repair.py tests/unit/ 2>/dev/null || true
git mv tests/test_blocksworld_physics_validator.py tests/unit/ 2>/dev/null || true

# 集成测试
git mv tests/test_integration.py tests/integration/ 2>/dev/null || true
git mv tests/test_integration_phase2.py tests/integration/ 2>/dev/null || true
git mv tests/test_integrated_verification.py tests/integration/ 2>/dev/null || true
git mv tests/test_symbolic_verifier_integration.py tests/integration/ 2>/dev/null || true
git mv tests/test_val_integration.py tests/integration/ 2>/dev/null || true

# 冒烟测试
git mv tests/smoke_test_cycle_repair.py tests/smoke/ 2>/dev/null || true

git commit -m "reorg: batch5+6 - clean src/ root, restructure tests/ into unit/integration/smoke"
```

---

## Task 6: Batch 7 — 创建 pyproject.toml

替代残缺的 `requirements.txt`（仅 4 个依赖）。

创建 `pyproject.toml`:
```toml
[project]
name = "bdi-llm-formal-ver"
version = "0.1.0"
description = "PNSV: Pluggable Neuro-Symbolic Verification for LLM-generated plans"
requires-python = ">=3.10"

dependencies = [
    "dspy-ai>=2.4",
    "networkx>=3.0",
    "pydantic>=2.0",
    "litellm>=1.0",
    "openai>=1.0",
    "python-dotenv>=1.0",
    "z3-solver>=4.12",
    "mcp>=0.1",
    "pyyaml>=6.0",
    "requests>=2.28",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "docker>=7.0",
    "ruff>=0.1",
]

[tool.ruff]
line-length = 100
select = ["E", "W", "F", "I", "C90", "UP", "B"]

[tool.ruff.mccabe]
max-complexity = 15

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
```

Then:
```bash
cd /Users/alexjiang/Desktop/BDI_LLM_Formal_Ver
git add pyproject.toml
git commit -m "reorg: batch7 - add pyproject.toml replacing incomplete requirements.txt"
```

---

## Task 7: Batch 8 — 引用修复

搜索并修复所有因文件移动而断裂的路径引用。

```bash
cd /Users/alexjiang/Desktop/BDI_LLM_Formal_Ver

# 搜索需要更新的旧路径引用
rg -n "C4-Documentation|conductor/|scripts/run_planbench_full|scripts/test_|src/mcp_server|phase1_archive" \
  README.md README_CN.md CLAUDE.md GEMINI.md docs/ .agent/ .agents/ 2>/dev/null || true
```

Based on the rg output, update all broken references in README.md, CLAUDE.md, GEMINI.md, and any docs/ files. Also update import paths in any Python files that use `from scripts.run_planbench_full import ...` to use `from scripts.evaluation.run_planbench_full import ...`.

Also check and update imports in:
- `scripts/evaluation/run_verification_only.py` — update its imports from `scripts.run_planbench_full`
- `scripts/replanning/run_dynamic_replanning.py` — update its imports similarly

```bash
git add -A
git commit -m "reorg: batch8 - fix broken references and import paths"
```

---

## Task 8: Batch 9 — Phase 2 验证

Run the reorg validation checklist:

1. **Root cleanliness**: `ls -1 /Users/alexjiang/Desktop/BDI_LLM_Formal_Ver/ | wc -l` — target ≤ 15 top-level items
2. **Gitignore**: Verify generated/local artifacts are excluded: `git status` should be clean after commit
3. **Path references**: `rg -n "C4-Documentation|conductor/" README.md CLAUDE.md GEMINI.md docs/` should return 0 hits
4. **Git status**: `git status` should only show expected changes
5. **Imports**: Run `python3 -c "from src.bdi_llm.planner import BDIPlanner; print('OK')"` to verify core imports work
6. **Tests**: Run `pytest tests/ -v --tb=short 2>&1 | head -50` and report results

Report all results clearly. If any tests fail due to import path changes, fix them.

```bash
git add -A && git commit -m "reorg: batch9 - phase2 validation fixes" 2>/dev/null || true
```

---

## Task 9: Target 1 — 拆分 planner.py → planner/ 子包

**This is the most critical and complex refactoring task.**

Split `src/bdi_llm/planner.py` (1699 lines) into a `planner/` sub-package:

```
src/bdi_llm/planner/
├── __init__.py        # Re-export BDIPlanner, configure_dspy for backward compat
├── prompts.py         # _GRAPH_STRUCTURE_COMMON, _STATE_TRACKING_HEADER, _LOGICOT_HEADER, etc.
├── signatures.py      # GeneratePlan, GeneratePlanLogistics, GeneratePlanDepots
├── lm_adapter.py      # ResponsesAPILM class
├── dspy_config.py     # configure_dspy() function
└── bdi_engine.py      # BDIPlanner class
```

Steps:
1. Create the package directory `src/bdi_llm/planner/`
2. Extract shared prompt constants to `prompts.py`
3. Extract `ResponsesAPILM` to `lm_adapter.py`  
4. Extract `configure_dspy()` to `dspy_config.py`
5. Extract the 3 DSPy Signatures to `signatures.py` (imports from `prompts.py`)
6. Move `BDIPlanner` class to `bdi_engine.py` (imports from signatures, lm_adapter, dspy_config)
7. Create `__init__.py` that re-exports: `from .bdi_engine import BDIPlanner` and `from .dspy_config import configure_dspy`
8. Delete old `src/bdi_llm/planner.py`
9. Update `coding_planner.py` to import from `.planner.prompts` instead of private `_` symbols
10. Run `python3 -c "from src.bdi_llm.planner import BDIPlanner; print('OK')"` to verify
11. Run `pytest tests/ -v --tb=short` to verify no regressions

```bash
git add -A
git commit -m "refactor: target1 - split planner.py into planner/ sub-package"
```

---

## Task 10: Target 2 — 提取 planbench_utils/ 公共库

Extract shared utilities from `scripts/evaluation/run_planbench_full.py` into a reusable package.

Create:
```
scripts/evaluation/planbench_utils/
├── __init__.py
├── pddl_parser.py      # parse_pddl_problem, find_all_instances, resolve_domain_file
├── pddl_to_nl.py       # pddl_to_nl_blocksworld, pddl_to_nl_logistics, pddl_to_nl_depots, pddl_to_natural_language
├── bdi_to_pddl.py      # bdi_to_pddl_actions
└── tqdm_compat.py       # Unified tqdm/dummy-tqdm compatible import
```

Steps:
1. Create the package directory
2. Extract the PDDL parsing functions to `pddl_parser.py`
3. Extract the NL conversion functions to `pddl_to_nl.py`
4. Extract `bdi_to_pddl_actions` to `bdi_to_pddl.py`
5. Create `tqdm_compat.py` with the unified tqdm import
6. Update `run_planbench_full.py` to import from `planbench_utils`
7. Update `scripts/evaluation/run_verification_only.py` to import from `planbench_utils` instead of `scripts.run_planbench_full`
8. Update `scripts/replanning/run_dynamic_replanning.py` similarly
9. Verify: `python3 -c "from scripts.evaluation.planbench_utils.pddl_parser import parse_pddl_problem; print('OK')"`

```bash
git add -A
git commit -m "refactor: target2 - extract planbench_utils/ shared library from run_planbench_full.py"
```

---

## Task 11: Target 3+4+5 — MCP统一 + symbolic_verifier + api_budget

Three medium-risk refactorings:

**Target 3: MCP Server**
- `src/mcp_server.py` and `src/mcp_server_bdi.py` were already archived in Task 5
- Verify `src/interfaces/mcp_server.py` is the single canonical MCP server
- Replace `sys.path.append(...)` with proper relative imports

**Target 4: symbolic_verifier.py**
- Extract `_run_val()`, temporary file management, and VAL output parsing into `src/bdi_llm/val_runner.py`
- Keep `PDDLSymbolicVerifier`, `BlocksworldPhysicsValidator`, and `IntegratedVerifier` in `symbolic_verifier.py`

**Target 5: api_budget.py**
- Extract `RepairCache` class into `src/bdi_llm/repair_cache.py`
- Update imports in `planner.py` (now `planner/bdi_engine.py`) that use RepairCache

Verify after each:
```bash
pytest tests/ -v --tb=short
python3 -c "from src.bdi_llm.symbolic_verifier import PDDLSymbolicVerifier; print('OK')"
```

```bash
git add -A
git commit -m "refactor: target3+4+5 - unify MCP, extract val_runner, extract RepairCache"
```

---

## Task 12: Target 6 — batch_engine.py 去硬编码 + 统一 DAG 解析

Refactor `src/bdi_llm/batch_engine.py`:

1. Replace hardcoded `model="qwen3.5-plus"` and `base_url="https://dashscope..."` with `Config.MODEL_NAME` and `Config.OPENAI_API_BASE`
2. Move `parse_plan_from_text()` to `src/bdi_llm/schemas.py` as `BDIPlan.from_llm_text(raw: str) -> BDIPlan` classmethod (Issue A)
3. Update `batch_engine.py` to use `BDIPlan.from_llm_text()`
4. Update `src/bdi_llm/dynamic_replanner/replanner.py` to use `BDIPlan.from_llm_text()` instead of inline JSON parsing
5. Fix `replanner.py` hardcoded model fallback: replace `getattr(Config, 'LLM_MODEL', 'qwen3.5-plus')` with `Config.MODEL_NAME` (Issue B)

Verify:
```bash
python3 -c "from src.bdi_llm.schemas import BDIPlan; print(hasattr(BDIPlan, 'from_llm_text'))"
pytest tests/ -v --tb=short
```

```bash
git add -A
git commit -m "refactor: target6 + issueA+B - unify DAG parsing, remove hardcoded config"
```

---

## Task 13: Target 7+8+9 — coding_planner + 评估脚本去重

**Target 7**: Update `src/bdi_llm/coding_planner.py` imports:
- Change `from .planner import BDIPlanner, _GRAPH_STRUCTURE_COMMON, ...` to `from .planner import BDIPlanner` and `from .planner.prompts import _GRAPH_STRUCTURE_COMMON, ...`

**Target 8+9**: Update evaluation scripts to use `planbench_utils/tqdm_compat.py`:
- Remove duplicate dummy `tqdm` class from `scripts/evaluation/run_verification_only.py`
- Remove duplicate dummy `tqdm` class from `scripts/replanning/run_dynamic_replanning.py`
- Replace with `from scripts.evaluation.planbench_utils.tqdm_compat import tqdm` (Issue C)

Verify:
```bash
python3 -c "from src.bdi_llm.coding_planner import CodingBDIPlanner; print('OK')"
pytest tests/ -v --tb=short
```

```bash
git add -A
git commit -m "refactor: target7+8+9 + issueC - fix coding_planner imports, deduplicate tqdm"
```

---

## Task 14: Issue D — 消除 sys.path hack

Replace all `sys.path.append(...)` / `sys.path.insert(0, ...)` with proper Python packaging:

1. Verify `pyproject.toml` exists (created in Task 6)
2. Add `[tool.setuptools.packages.find]` section to make the package installable
3. Run `pip install -e .` to install in editable mode
4. Remove `sys.path` hacks from:
   - `src/interfaces/mcp_server.py`
   - `src/interfaces/cli.py`
   - Any `scripts/*.py` files that use `sys.path.insert(0, ...)`
5. Replace with proper relative or absolute imports

Verify:
```bash
python3 -c "from src.bdi_llm.planner import BDIPlanner; print('OK')"
python3 -c "from src.interfaces.mcp_server import mcp; print('OK')"
pytest tests/ -v --tb=short
```

```bash
git add -A
git commit -m "refactor: issueD - remove sys.path hacks, use editable install"
```

---

## Task 15: 最终验证

Run comprehensive verification:

1. **Import checks**:
```bash
python3 -c "from src.bdi_llm.planner import BDIPlanner; print('planner OK')"
python3 -c "from src.bdi_llm.symbolic_verifier import PDDLSymbolicVerifier, IntegratedVerifier; print('verifier OK')"
python3 -c "from src.bdi_llm.schemas import BDIPlan; print('schemas OK')"
python3 -c "from src.bdi_llm.config import Config; print('config OK')"
python3 -c "from src.bdi_llm.batch_engine import BatchEngine; print('batch OK')"
python3 -c "from src.bdi_llm.coding_planner import CodingBDIPlanner; print('coding OK')"
python3 -c "from src.interfaces.mcp_server import mcp; print('mcp OK')"
```

2. **Full test suite**: `pytest tests/ -v --tb=short`
3. **Root cleanliness**: `ls -1 | wc -l` (target ≤ 15)
4. **Git log review**: `git log --oneline -20` to verify all commits are clean

Report results. If anything fails, fix it and commit.

```bash
git add -A && git commit -m "reorg: final validation and cleanup" 2>/dev/null || true
```
