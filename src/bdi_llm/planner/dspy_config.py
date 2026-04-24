"""Idempotent DSPy configuration for BDI planning."""

import dspy

from ..config import Config
from .lm_adapter import ResponsesAPILM

# Module-level flag to ensure DSPy is configured only once
_dspy_configured: bool = False
_REASONING_MODEL_TAGS = (
    "gpt-5",
    "gpt-oss",
    "o1",
    "o3",
    "glm5",
    "glm-5",
    "glm47flash",
    "glm-4.7",
    "glm-4.7-flash",
    "z-ai/glm",
    "zai-org/glm",
)
_GLM_MODEL_TAGS = (
    "glm5",
    "glm-5",
    "glm47flash",
    "glm-4.7",
    "glm-4.7-flash",
    "z-ai/glm",
    "zai-org/glm",
)


def _model_has_any_tag(model_name: str, tags: tuple[str, ...]) -> bool:
    model_name_lower = model_name.lower()
    return any(tag in model_name_lower for tag in tags)


def configure_dspy():
    """
    Idempotently configure DSPy for use by BDIPlanner.

    Subsequent calls are effectively no-ops once configuration has been
    successfully completed in this process.
    """
    global _dspy_configured
    if _dspy_configured:
        # DSPy already configured in this process; reuse existing configuration
        return

    # 1. Configure DSPy
    # Validate configuration in non-strict mode so parser/unit tests can import
    # planner utilities without requiring live API credentials.
    credentials = Config.validate(require_credentials=False)

    # Check if model is a reasoning model (gpt-5, o1, etc.)
    model_name_lower = Config.MODEL_NAME.lower()
    is_reasoning_model = _model_has_any_tag(Config.MODEL_NAME, _REASONING_MODEL_TAGS)

    # Check if model is a Gemini model
    is_gemini_model = "gemini" in model_name_lower

    # Check if model uses Vertex AI (vertex_ai/ prefix)
    is_vertex_ai = model_name_lower.startswith("vertex_ai/")

    # Check if model uses NVIDIA API (nvidia/ prefix or integrate.api.nvidia.com)
    is_nvidia_api = model_name_lower.startswith("nvidia/") or (
        Config.OPENAI_API_BASE and "nvidia" in Config.OPENAI_API_BASE.lower()
    )
    is_glm_model = _model_has_any_tag(Config.MODEL_NAME, _GLM_MODEL_TAGS)
    glm_chat_template_kwargs = (
        {"enable_thinking": True, "clear_thinking": False} if is_glm_model and Config.ENABLE_THINKING else None
    )

    # Prepare LM configuration based on model type
    lm_config = {
        "model": Config.MODEL_NAME,
        "seed": Config.SEED,
    }

    # Add API key based on model type
    # Vertex AI models use service account credentials via env vars (no api_key needed)
    if is_vertex_ai:
        # litellm reads GOOGLE_APPLICATION_CREDENTIALS, VERTEXAI_PROJECT,
        # and VERTEXAI_LOCATION from environment variables.
        pass
    elif is_gemini_model and credentials["google"]:
        lm_config["api_key"] = credentials["google"]
    elif credentials["openai"]:
        lm_config["api_key"] = credentials["openai"]
        if Config.OPENAI_API_BASE:
            lm_config["api_base"] = Config.OPENAI_API_BASE

    # Add model-specific parameters
    if is_reasoning_model:
        # NVIDIA API uses Chat Completions with streaming
        if is_nvidia_api:
            lm = ResponsesAPILM(
                model=Config.MODEL_NAME.replace("nvidia/", ""),
                api_key=credentials["openai"],
                api_base=Config.OPENAI_API_BASE or "https://integrate.api.nvidia.com/v1",
                reasoning_effort=Config.REASONING_EFFORT,
                max_tokens=Config.MAX_TOKENS,
                timeout=Config.TIMEOUT,
                num_retries=10,
                seed=Config.SEED,
                temperature=Config.TEMPERATURE,
                use_chat_completions=True,  # Use Chat Completions API for NVIDIA
                chat_template_kwargs=glm_chat_template_kwargs,
            )
            dspy.configure(lm=lm)
            _dspy_configured = True
            return
        # infiniteai Responses API path
        elif credentials["openai"] and Config.OPENAI_API_BASE:
            lm = ResponsesAPILM(
                model=Config.MODEL_NAME.replace("openai/", ""),
                api_key=credentials["openai"],
                api_base=Config.OPENAI_API_BASE,
                reasoning_effort=Config.REASONING_EFFORT,
                max_tokens=Config.MAX_TOKENS,
                timeout=Config.TIMEOUT,
                num_retries=10,
                seed=Config.SEED,
                temperature=Config.TEMPERATURE,
                use_chat_completions=is_glm_model,
                chat_template_kwargs=glm_chat_template_kwargs,
            )
            dspy.configure(lm=lm)
            _dspy_configured = True
            return
        else:
            lm_config["temperature"] = 1.0
            lm_config["max_tokens"] = 16000
            lm_config["reasoning_effort"] = "low"
    else:
        # Standard models use configured temperature for deterministic output
        lm_config["temperature"] = Config.TEMPERATURE
        lm_config["max_tokens"] = Config.MAX_TOKENS

    # Add max_tokens for gemini models
    if "gemini" in Config.MODEL_NAME.lower() or "vertex_ai" in Config.MODEL_NAME.lower():
        lm_config["max_tokens"] = 16000

    # Add timeout and retry settings for rate limiting and reliability
    # Configurable timeout (default 600s for reasoning models).
    lm_config["timeout"] = Config.TIMEOUT
    lm_config["num_retries"] = 10
    lm_config["extra_headers"] = {"User-Agent": "python-httpx/0.28.1"}

    lm = dspy.LM(**lm_config)
    dspy.configure(lm=lm)

    # Mark as configured after successful configuration
    _dspy_configured = True
