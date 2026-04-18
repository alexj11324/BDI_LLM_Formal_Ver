"""Tests for runtime controls in the OpenAI-compatible LM adapter."""

from __future__ import annotations

import json

from src.bdi_llm.planner.lm_adapter import ResponsesAPILM


class _FakeResponse:
    def raise_for_status(self):
        return None

    def iter_lines(self):
        payload = {
            "choices": [
                {
                    "delta": {
                        "content": "hello",
                    }
                }
            ]
        }
        yield f"data: {json.dumps(payload)}".encode()
        yield b"data: [DONE]"


def test_chat_completions_payload_includes_seed_and_temperature(monkeypatch):
    recorded: dict[str, object] = {}

    def fake_post(url, json=None, headers=None, stream=None, timeout=None):
        recorded["payload"] = json
        return _FakeResponse()

    lm = ResponsesAPILM(
        model="glm47flash",
        api_key="EMPTY",
        api_base="http://localhost:8000/v1",
        use_chat_completions=True,
        chat_template_kwargs={"enable_thinking": True, "clear_thinking": False},
        seed=42,
        temperature=0.0,
    )
    monkeypatch.setattr(lm._session, "post", fake_post)

    result = lm._call_once_chat_completions([{"role": "user", "content": "hello"}])

    assert result == "hello"
    assert recorded["payload"]["seed"] == 42
    assert recorded["payload"]["temperature"] == 0.0
