# Tech Stack

## Primary Language

- **Python 3.10+** — Strict type hints enforced on every function/method

## Frameworks & Libraries

### Core
- **DSPy** — LLM orchestration with ChainOfThought signatures for plan generation and repair
- **Pydantic V2** — Schema validation for IntentionDAG, BeliefState, VerificationResult
- **Z3 Solver** — Constraint solving (listed in requirements)

### Verification
- **VAL (Validator)** — External PDDL plan validator binary (macOS arm64, located in `planbench_data/`)
- **PDDL** — Planning Domain Definition Language for symbolic verification

### AI/ML
- **GLM-5 / GPT-5 / Gemini** — Teacher LLMs for plan generation (via DSPy)
- **DeepSeek-R1-Distill-Qwen-7B** — Target student model for distillation
- **NVIDIA NIM API** — Model serving gateway (Qwen2.5-7B-Instruct for evaluation)

### Infrastructure
- **MCP (Model Context Protocol)** — Server for agent integration
- **Docker** — Containerized deployment
- **pytest** — Test framework
- **MLflow** — Experiment tracking (mlflow.db present)

## Database

None / Stateless — Results stored as JSON files in `runs/` and `artifacts/`

## Deployment

- **Local execution** — Primary development and evaluation mode
- **Docker** — Containerized deployment available (Dockerfile present)
- **MCP Server** — `src/mcp_server_bdi.py` for agent integration

## Key Dependencies (from requirements.txt)

```
z3-solver
mcp
docker
pytest
```

## External Services

- OpenAI API (or compatible gateway: NVIDIA NIM, Anthropic, Google)
- VAL binary (bundled in `planbench_data/`)
