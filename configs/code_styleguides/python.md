# Python Code Style Guide

## General Rules

- **Python 3.10+** — Use modern type hints (union types with `|`, built-in generics)
- **Strict Type Hints** — Every function and method must have complete type annotations
- **Pydantic V2** — All data schemas use `BaseModel` (not dataclasses)

## Code Formatting

- **Line length**: 100 characters max
- **Indentation**: 4 spaces
- **Imports**: Group by stdlib → third-party → local, alphabetically within groups
- **Docstrings**: Google-style docstrings for all public functions

## Naming Conventions

- `snake_case` for functions, methods, variables, module names
- `PascalCase` for classes
- `UPPER_SNAKE_CASE` for constants
- Private members prefixed with `_`

## Architecture Rules

1. **Zero Domain Leakage**: `src/core/bdi_engine.py` must NEVER import domain-specific libraries
2. **Strategy Pattern**: Domain logic in `src/plugins/` only, accessed via `BaseDomainVerifier`
3. **State Immutability**: Verifiers operate on `copy.deepcopy()` of `BeliefState`
4. **Robust JSON Extraction**: Regex-based extraction (first `{` to last `}`) with `json.loads` fallback

## Testing

- Use `pytest` with fixtures
- Test files: `test_*.py` in `tests/` or `workspaces/pnsv_workspace/tests/`
- Integration tests auto-skip when API credentials unavailable
