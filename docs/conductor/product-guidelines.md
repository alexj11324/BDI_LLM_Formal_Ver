# Product Guidelines

## Voice and Tone

Professional and technical. Documentation should be precise, use formal language, and include mathematical/logical notation where appropriate. Suitable for an academic research project targeting AAAI 2026.

## Design Principles

1. **Zero Domain Leakage** — Core BDI engine must never import domain-specific libraries. All domain logic lives in plugins
2. **State Immutability** — Verifiers evaluate deep copies of BeliefState; canonical state is only mutated on successful verification
3. **Strategy Pattern** — Domain-specific logic resides in `symbolic_verifier.py` via `register_physics_validator()`, accessed through the `PHYSICS_VALIDATORS` registry
4. **Correctness Over Performance** — Formal correctness guarantees take priority over execution speed
5. **Complete BDI Loop** — The verify-repair cycle is a first-class feature, not an afterthought. Both verification and auto-repair live on `main`.
6. **Reproducibility** — All experiments must be fully reproducible with frozen evidence snapshots in `artifacts/`
7. **Pydantic V2 Everywhere** — All schemas use Pydantic V2 BaseModel for robust validation and serialization
