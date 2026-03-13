# Tech Stack

## Languages
- **Python 3.10+** (Primary) — Python 3.11 recommended

## Core Frameworks
| Framework | Version | Purpose |
|-----------|---------|---------|
| DSPy | latest | Structured LM programming, prompt optimization |
| Pydantic | V2 | Data validation and schema definition |
| NetworkX | latest | DAG representation and graph operations |
| Z3 Solver | latest | Formal constraint solving |

## External Tools
| Tool | Purpose |
|------|---------|
| VAL Binary | Classical PDDL plan validator (C++) |
| MCP Python SDK | Model Context Protocol server |

## Infrastructure
| Component | Technology |
|-----------|-----------|
| Containerization | Docker |
| CI/CD | GitHub Actions |
| Cloud | Oracle Cloud Infrastructure (ARM64) for batch evaluation |
| Package Management | pip + pyproject.toml (uv compatible) |
| Testing | Pytest |
| Linting | Ruff |

## LLM Providers
| Provider | Use Case |
|----------|----------|
| OpenAI / DashScope | Primary inference (gpt-5, qwq-plus) |
| Anthropic | Alternative inference (Claude) |
| Google | Alternative inference (Gemini) |

## Key Dependencies
- `dspy-ai` — structured LM programming
- `pydantic` — data validation
- `networkx` — graph operations
- `z3-solver` — formal verification
- `mcp` — Model Context Protocol SDK
- `datasets` — HuggingFace dataset loading
