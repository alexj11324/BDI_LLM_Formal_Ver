import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

class Config:
    """Central configuration for BDI-LLM Framework."""

    # API Configuration
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
    GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    # Model Configuration
    # Default to GPT-4o, but allow override
    MODEL_NAME = os.environ.get("LLM_MODEL", "openai/gpt-4o")
    MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "4000"))
    TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.2"))

    # Vertex AI Configuration
    VERTEXAI_PROJECT = os.environ.get("VERTEXAI_PROJECT")
    VERTEXAI_LOCATION = os.environ.get("VERTEXAI_LOCATION", "us-central1")

    # Tools Configuration
    # Auto-detect VAL in PlanBench if not provided in env
    # Base is repo root: src/bdi_llm/config.py -> src/bdi_llm -> src -> root
    _base_dir = Path(__file__).parent.parent.parent
    _default_val_path = _base_dir / "planbench_data/planner_tools/VAL/validate"

    VAL_VALIDATOR_PATH = os.environ.get("VAL_VALIDATOR_PATH") or os.environ.get("VAL") or str(_default_val_path)

    @classmethod
    def validate(cls):
        """Validate critical configuration."""
        if not cls.OPENAI_API_KEY and not cls.ANTHROPIC_API_KEY and not cls.GOOGLE_API_KEY and not cls.GOOGLE_APPLICATION_CREDENTIALS:
             raise ValueError(
                "Missing API Key. Please set OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, or GOOGLE_APPLICATION_CREDENTIALS in environment or .env file."
            )

