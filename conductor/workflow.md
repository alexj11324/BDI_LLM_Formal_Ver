# Workflow

## TDD Policy

**Moderate** — Tests encouraged for all core logic. The project has 90+ unit tests in `pnsv_workspace/tests/` and integration tests in `tests/`. Tests should be written for verification logic and new domain verifiers.

## Commit Strategy

**Conventional Commits** — Use `feat:`, `fix:`, `refactor:`, `docs:`, `test:` prefixes.

## Code Review

**Required for non-trivial changes** — PRs required for core engine changes, verifier logic modifications, and new domain plugin additions.

## Verification Checkpoints

**After each phase completion** — Verify with `pytest` after major changes. Integration tests may be skipped when API credentials are unavailable.

## Task Lifecycle

1. **Spec** → Define the task requirements
2. **Plan** → Create implementation plan with file-level changes
3. **Implement** → Write code following architecture principles (zero domain leakage, strategy pattern)
4. **Test** → Run `pytest` (unit + integration where applicable)
5. **Review** → PR review for non-trivial changes
6. **Merge** → Squash or conventional merge

## Development Methodology

- **Ralph AI Agent Loop** (Fresh Context) recommended for complex multi-modular work
- **Pseudo Ralph** discouraged due to context window exhaustion risk
