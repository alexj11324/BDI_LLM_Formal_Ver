# PNSV Framework Implementation Instructions

## Core Rules

1. **Zero Domain Leakage**: `src/core/bdi_engine.py` must NEVER import domain-specific libraries (pytest, ast, pddl). It only knows about generic dicts, Pydantic DAGs, and the `BaseDomainVerifier` interface.
2. **State Immutability**: Always pass deep copies of BeliefState to verifiers. Only commit changes on `is_valid == True`.
3. **Strategy Pattern**: All domain logic lives in `src/plugins/`. The core engine uses dependency injection.
4. **Pydantic V2**: All schemas must use Pydantic V2 `BaseModel`.
5. **Python 3.10+ type hints**: Every function and method must have strict type hints.
6. **Robust JSON Extraction**: Implement regex-based extraction (first `{` to last `}`) with `json.loads` fallback. Never crash on malformed LLM output.

## Workflow

- Complete exactly ONE task per iteration as defined in PRD.md.
- After completing a task, append progress to progress.txt.
- Follow the task numbering order (Task 1 → Task 2 → ... → Task 11).
- Each task should produce working, tested code.
- Run `python -c "import src.core.schemas"` (or similar) after each task to verify imports work.

## Code Quality

- Use descriptive docstrings for all public classes and methods.
- Follow PEP 8 style.
- Include inline comments for non-obvious logic.
