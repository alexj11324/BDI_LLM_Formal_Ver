import os
import re
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()


def _resolve_key(*env_names: str) -> str | None:
    """Read the first valid value from a sequence of env-var names.

    Skips values that look like un-expanded shell references (e.g. '${VAR}')
    because python-dotenv does NOT perform variable interpolation.
    """
    for name in env_names:
        val = os.environ.get(name)
        if val and not re.search(r"\$\{.+\}", val):
            return val
    return None


class Config:
    """Central configuration for BDI-LLM Framework."""

    # API Configuration
    OPENAI_API_KEY = _resolve_key("OPENAI_API_KEY")
    OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE")
    ANTHROPIC_API_KEY = _resolve_key("ANTHROPIC_API_KEY")
    GOOGLE_API_KEY = _resolve_key("GOOGLE_API_KEY")
    GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

    # Model Configuration
    # Default to GPT-4o, but allow override
    MODEL_NAME = os.environ.get("LLM_MODEL", "openai/gpt-4o")
    MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "4000"))
    TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.2"))
    SEED = int(os.environ.get("LLM_SEED", "42"))
    ENABLE_THINKING = os.environ.get("LLM_ENABLE_THINKING", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    REASONING_EFFORT = os.environ.get("REASONING_EFFORT", "medium")
    TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "600"))
    SAVE_REASONING_TRACE = os.environ.get("SAVE_REASONING_TRACE", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    REASONING_TRACE_MAX_CHARS = int(os.environ.get("REASONING_TRACE_MAX_CHARS", "8000"))

    # Vertex AI Configuration
    VERTEXAI_PROJECT = os.environ.get("VERTEXAI_PROJECT")
    VERTEXAI_LOCATION = os.environ.get("VERTEXAI_LOCATION", "us-central1")

    # API Budget Configuration (for rate limiting and caching)
    API_BUDGET_MAX_CALLS_PER_INSTANCE = int(os.environ.get("API_BUDGET_MAX_CALLS_PER_INSTANCE", "5"))
    API_BUDGET_MAX_RPM = int(os.environ.get("API_BUDGET_MAX_RPM", "60"))
    API_BUDGET_MAX_RPH = int(os.environ.get("API_BUDGET_MAX_RPH", "1000"))
    API_BUDGET_CACHE_ENABLED = os.environ.get("API_BUDGET_CACHE_ENABLED", "true").lower() == "true"
    API_BUDGET_EARLY_EXIT_ENABLED = os.environ.get("API_BUDGET_EARLY_EXIT_ENABLED", "true").lower() == "true"

    # Tools Configuration
    # Auto-detect VAL in PlanBench if not provided in env
    # Base is repo root: src/bdi_llm/config.py -> src/bdi_llm -> src -> root
    _base_dir = Path(__file__).parent.parent.parent
    _default_val_path = _base_dir / "workspaces/planbench_data/planner_tools/VAL/validate"

    VAL_VALIDATOR_PATH = os.environ.get("VAL_VALIDATOR_PATH") or os.environ.get("VAL") or str(_default_val_path)

    @classmethod
    def get_credentials(cls):
        """Read credentials from current environment with class-level fallback."""
        return {
            "openai": _resolve_key("OPENAI_API_KEY") or cls.OPENAI_API_KEY,
            "anthropic": _resolve_key("ANTHROPIC_API_KEY") or cls.ANTHROPIC_API_KEY,
            "google": _resolve_key("GOOGLE_API_KEY") or cls.GOOGLE_API_KEY,
            "google_application_credentials": (
                os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or cls.GOOGLE_APPLICATION_CREDENTIALS
            ),
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
                "Missing API Key. Please set OPENAI_API_KEY, ANTHROPIC_API_KEY, "
                "GOOGLE_API_KEY, or GOOGLE_APPLICATION_CREDENTIALS in environment "
                "or .env file."
            )
        return creds
