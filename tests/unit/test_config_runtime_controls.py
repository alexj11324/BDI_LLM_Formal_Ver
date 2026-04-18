"""Tests for runtime control flags exposed via Config."""

from __future__ import annotations

import importlib


def test_config_reads_seed_and_thinking_flags(monkeypatch):
    monkeypatch.setenv("LLM_SEED", "7")
    monkeypatch.setenv("LLM_ENABLE_THINKING", "false")

    config_module = importlib.import_module("src.bdi_llm.config")
    config_module = importlib.reload(config_module)

    assert config_module.Config.SEED == 7
    assert config_module.Config.ENABLE_THINKING is False
