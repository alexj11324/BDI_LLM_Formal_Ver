import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

class Config:
    """Central configuration for BDI-LLM Framework."""
    
    # API Configuration
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    OPENAI_API_BASE = os.environ.get("OPENAI_API_BASE")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
    
    # Model Configuration
    # Default to GPT-4o, but allow override
    MODEL_NAME = os.environ.get("LLM_MODEL", "openai/gpt-4o")
    MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "4000"))
    
    @classmethod
    def validate(cls):
        """Validate critical configuration."""
        if not cls.OPENAI_API_KEY and not cls.ANTHROPIC_API_KEY:
             raise ValueError(
                "Missing API Key. Please set OPENAI_API_KEY or ANTHROPIC_API_KEY in environment or .env file."
            )

