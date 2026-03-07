# Tech Stack

## Primary Language

- **Python 3.10+** — Strict type hints enforced on every function/method

## Frameworks & Libraries

### Core
- **DSPy (dspy-ai ≥2.4)** — LLM orchestration with ChainOfThought signatures for plan generation and repair
- **Pydantic V2 (≥2.0)** — Schema validation for BDIPlan, ActionNode, DependencyEdge, VerificationResult
- **NetworkX (≥3.0)** — DAG construction, cycle detection, topological sort
- **LiteLLM (≥1.0)** — Multi-provider LLM abstraction
- **OpenAI SDK (≥1.0)** — DashScope-compatible API client (plan generation, batch inference, dynamic replanning)
- **Z3 Solver (≥4.12)** — Constraint solving (dependency)

### Verification
- **VAL (Validator)** — External PDDL plan validator binary (macOS arm64)
- **PDDL** — Planning Domain Definition Language for symbolic verification

### AI/ML Providers
- **DashScope (qwq-plus)** — Primary plan generation & batch inference via OpenAI-compatible API
- **OpenAI (GPT-4o)** — Alternative provider
- **Anthropic (Claude)** — Alternative provider
- **Google (Gemini / Vertex AI)** — Paper canonical numbers

### Infrastructure
- **MCP (Model Context Protocol)** — FastMCP server for agent integration
- **Docker** — Containerized deployment
- **pytest (≥7.0)** — Test framework
- **Ruff (≥0.1)** — Linter and formatter
- **PyYAML (≥6.0)** — Configuration file parsing
- **python-dotenv (≥1.0)** — Environment variable management

## Database

None / Stateless — Results stored as JSON/CSV files in `runs/` and `artifacts/`

## Deployment

- **Local execution** — Primary development and evaluation mode
- **Docker** — Containerized deployment (Dockerfile present)
- **MCP Server** — `src/interfaces/mcp_server.py` for agent integration
- **DashScope Batch API** — Large-scale parallel inference via `scripts/batch/`

## Key Dependencies (from pyproject.toml)

```toml
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
```

## External Services

- DashScope API (OpenAI-compatible: `DASHSCOPE_API_KEY`)
- OpenAI / Anthropic / Google APIs (optional alternative providers)
- VAL binary (auto-detected via `Config._default_val_path`)
