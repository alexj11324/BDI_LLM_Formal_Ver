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
    def get_credentials(cls):
        """Read credentials from current environment with class-level fallback."""
        return {
            "openai": os.environ.get("OPENAI_API_KEY") or cls.OPENAI_API_KEY,
            "anthropic": os.environ.get("ANTHROPIC_API_KEY") or cls.ANTHROPIC_API_KEY,
            "google": os.environ.get("GOOGLE_API_KEY") or cls.GOOGLE_API_KEY,
            "google_application_credentials": os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or cls.GOOGLE_APPLICATION_CREDENTIALS,
        }

    @classmethod
    def validate(cls, require_credentials: bool = True):
        """Validate critical configuration.

        Args:
            require_credentials: if False, validation is best-effort and never raises.
        """
        creds = cls.get_credentials()
        if require_credentials and not any(creds.values()):
            raise ValueError(
                "Missing API Key. Please set OPENAI_API_KEY, ANTHROPIC_API_KEY, GOOGLE_API_KEY, or GOOGLE_APPLICATION_CREDENTIALS in environment or .env file."
            )
        return creds
