# Product Guidelines

## Voice and Tone
Professional and technical. Research-grade precision in terminology. Code comments and documentation should be concise and direct.

## Design Principles
1. **Correctness over speed** — Every plan must pass formal verification before execution
2. **Pluggable domains** — New domains should integrate by adding a `DomainSpec`, not modifying the engine
3. **Reproducibility** — All benchmark results must be traceable to exact source files and configurations
4. **Simplicity** — Keep logic strictly verified; avoid unnecessary abstraction layers
5. **Transparency** — Log full reasoning traces for every verification trajectory
