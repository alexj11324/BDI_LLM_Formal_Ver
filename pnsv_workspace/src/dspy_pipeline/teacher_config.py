"""DSPy Teacher LLM configuration for the PNSV framework.

This module provides factory functions that initialise a DSPy language-model
backend and configure it as the global default for teacher invocations.

The primary entry-point is :func:`init_glm5_teacher`, which sets up a GLM-5
(or GLM-4) model via its OpenAI-compatible API.  A generic helper,
:func:`init_openai_compatible_teacher`, is also exposed so that the same
pattern can be reused for any OpenAI-compatible endpoint (vLLM, Ollama,
Together AI, etc.).

Usage
-----
.. code-block:: python

    from src.dspy_pipeline.teacher_config import init_glm5_teacher

    lm = init_glm5_teacher(api_key="your-zhipu-api-key")
    # DSPy is now globally configured to use GLM-5.

Design notes
------------
* The module only depends on **dspy** (which in turn vendors ``litellm``).
  No domain-specific imports are present.
* All functions return the constructed :class:`dspy.LM` so callers can
  inspect or override settings if needed.
* Temperature, ``max_tokens``, and other generation parameters are
  deliberately exposed as keyword arguments with sensible defaults for
  agentic plan-generation workloads (low temperature, generous token
  budget).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import dspy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default constants
# ---------------------------------------------------------------------------

DEFAULT_GLM_API_BASE: str = "https://open.bigmodel.cn/api/paas/v4/"
"""Default OpenAI-compatible base URL for ZhipuAI's GLM family."""

DEFAULT_GLM_MODEL: str = "openai/glm-4"
"""Default model identifier used by DSPy/LiteLLM for the GLM endpoint.

DSPy expects an ``openai/<model>`` prefix when routing through an
OpenAI-compatible API.
"""

DEFAULT_TEMPERATURE: float = 0.3
"""Conservative temperature for structured-plan generation."""

DEFAULT_MAX_TOKENS: int = 4096
"""Generous token budget to accommodate complex DAG JSON output."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def init_glm5_teacher(
    api_key: str,
    api_base: str = DEFAULT_GLM_API_BASE,
    *,
    model: str = DEFAULT_GLM_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    configure_globally: bool = True,
    extra_kwargs: Optional[Dict[str, Any]] = None,
) -> dspy.LM:
    """Initialise a DSPy Language Model targeting ZhipuAI's GLM-5 / GLM-4.

    The function creates a :class:`dspy.LM` instance configured to
    communicate with the GLM family through its OpenAI-compatible REST
    endpoint, and (by default) registers it as the global DSPy LM via
    :func:`dspy.configure`.

    Parameters
    ----------
    api_key : str
        ZhipuAI API key.  Obtain one from
        ``https://open.bigmodel.cn/usercenter/apikeys``.
    api_base : str, optional
        Base URL of the OpenAI-compatible endpoint.  Defaults to
        :data:`DEFAULT_GLM_API_BASE`.
    model : str, optional
        The ``<provider>/<model>`` identifier that DSPy/LiteLLM uses to
        route requests.  Defaults to ``"openai/glm-4"``.
    temperature : float, optional
        Sampling temperature.  Lower values produce more deterministic
        plans. Defaults to :data:`DEFAULT_TEMPERATURE`.
    max_tokens : int, optional
        Maximum number of tokens in the response.  Defaults to
        :data:`DEFAULT_MAX_TOKENS`.
    configure_globally : bool, optional
        If ``True`` (the default), call :func:`dspy.configure` so that all
        subsequent DSPy modules use this LM automatically.
    extra_kwargs : Dict[str, Any] | None, optional
        Any additional keyword arguments forwarded to :class:`dspy.LM`
        (e.g. ``top_p``, ``stop``, ``cache``).

    Returns
    -------
    dspy.LM
        The configured language-model instance.

    Examples
    --------
    >>> lm = init_glm5_teacher(api_key="sk-xxxxx")  # doctest: +SKIP
    >>> lm("What is 2 + 2?")  # doctest: +SKIP
    """
    return init_openai_compatible_teacher(
        model=model,
        api_key=api_key,
        api_base=api_base,
        temperature=temperature,
        max_tokens=max_tokens,
        configure_globally=configure_globally,
        extra_kwargs=extra_kwargs,
    )


def init_openai_compatible_teacher(
    model: str,
    api_key: str,
    api_base: str,
    *,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    configure_globally: bool = True,
    extra_kwargs: Optional[Dict[str, Any]] = None,
) -> dspy.LM:
    """Initialise a DSPy Language Model targeting any OpenAI-compatible API.

    This is the generic factory behind :func:`init_glm5_teacher`.  It can
    be reused to point DSPy at vLLM, Ollama, Together AI, or any other
    endpoint that speaks the OpenAI Chat Completions protocol.

    Parameters
    ----------
    model : str
        The ``<provider>/<model>`` identifier for DSPy/LiteLLM routing
        (e.g. ``"openai/glm-4"``, ``"openai/my-local-llama"``).
    api_key : str
        API key for the target endpoint.  Pass an empty string for
        unauthenticated local servers.
    api_base : str
        Base URL of the OpenAI-compatible endpoint (e.g.
        ``"http://localhost:8000/v1"``).
    temperature : float, optional
        Sampling temperature.  Defaults to :data:`DEFAULT_TEMPERATURE`.
    max_tokens : int, optional
        Maximum response tokens.  Defaults to :data:`DEFAULT_MAX_TOKENS`.
    configure_globally : bool, optional
        If ``True`` (the default), register the LM globally via
        :func:`dspy.configure`.
    extra_kwargs : Dict[str, Any] | None, optional
        Additional keyword arguments forwarded to :class:`dspy.LM`.

    Returns
    -------
    dspy.LM
        The configured language-model instance.

    Raises
    ------
    ValueError
        If *model* or *api_base* are empty strings.
    """
    if not model:
        raise ValueError("'model' must be a non-empty string.")
    if not api_base:
        raise ValueError("'api_base' must be a non-empty string.")

    # Build the kwargs for dspy.LM.
    lm_kwargs: Dict[str, Any] = {
        "api_key": api_key,
        "api_base": api_base,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if extra_kwargs:
        lm_kwargs.update(extra_kwargs)

    lm: dspy.LM = dspy.LM(model, **lm_kwargs)

    logger.info(
        "DSPy LM initialised: model=%s, api_base=%s, temperature=%.2f, "
        "max_tokens=%d",
        model,
        api_base,
        temperature,
        max_tokens,
    )

    if configure_globally:
        dspy.configure(lm=lm)
        logger.info("DSPy globally configured with model '%s'.", model)

    return lm
