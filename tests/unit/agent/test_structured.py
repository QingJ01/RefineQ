"""Strict parsing contracts for structured model operations."""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict

from refineq.agent.settings import ModelSettings
from refineq.agent.structured import (
    OpenAICompatibleStructuredTransport,
    StructuredModelResponseError,
    parse_structured_reply,
)


class RoutingAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["reuse", "create"]
    reason: str


@pytest.mark.parametrize(
    "text",
    [
        '{"action":"reuse","reason":"same subject"}',
        '```json\n{"action":"create","reason":"new subject"}\n```',
        'Result:\n{"action":"reuse","reason":"same context"}\nDone.',
    ],
)
def test_structured_reply_accepts_plain_fenced_and_embedded_json(text: str) -> None:
    parsed = parse_structured_reply(text, RoutingAnswer)

    assert parsed.action in {"reuse", "create"}
    assert parsed.reason


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"action":"delete","reason":"unsupported"}',
        '{"action":"reuse","reason":"ok","owner_id":"attacker"}',
    ],
)
def test_structured_reply_rejects_invalid_or_schema_escaping_output(text: str) -> None:
    with pytest.raises(StructuredModelResponseError):
        parse_structured_reply(text, RoutingAnswer)


def test_structured_transport_uses_finite_timeout_retry_and_output_budget(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            captured["request"] = kwargs
            message = type("Message", (), {"content": '{"action":"create","reason":"new"}'})
            choice = type("Choice", (), {"message": message})
            return type("Response", (), {"choices": [choice]})

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            captured["client"] = kwargs
            self.chat = type("Chat", (), {"completions": FakeCompletions()})

    monkeypatch.setattr("refineq.agent.structured.OpenAI", FakeOpenAI)

    result = OpenAICompatibleStructuredTransport().complete(
        settings=ModelSettings(
            base_url="https://api.openai.com/v1",
            model="exam-tutor",
            api_key="secret",
        ),
        messages=[{"role": "user", "content": "route this"}],
        response_model=RoutingAnswer,
    )

    assert result.action == "create"
    assert captured["client"]["timeout"] <= 30
    assert captured["client"]["max_retries"] <= 2
    assert captured["request"]["max_tokens"] <= 4_000

    sent_messages = captured["request"]["messages"]
    schema_instruction = sent_messages[-1]["content"]
    assert sent_messages[-1]["role"] == "system"
    assert "JSON" in schema_instruction
    assert '"action"' in schema_instruction
    assert '"reason"' in schema_instruction
    assert '"additionalProperties": false' in schema_instruction


def test_structured_transport_accepts_short_lived_client_configuration(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            del kwargs
            message = type("Message", (), {"content": '{"action":"create","reason":"new"}'})
            choice = type("Choice", (), {"message": message})
            return type("Response", (), {"choices": [choice]})

    class FakeOpenAI:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)
            self.chat = type("Chat", (), {"completions": FakeCompletions()})

    monkeypatch.setattr("refineq.agent.structured.OpenAI", FakeOpenAI)

    OpenAICompatibleStructuredTransport(timeout=8.0, max_retries=0).complete(
        settings=ModelSettings(
            base_url="https://api.openai.com/v1",
            model="exam-tutor",
            api_key="secret",
        ),
        messages=[{"role": "user", "content": "route this"}],
        response_model=RoutingAnswer,
    )

    assert captured["timeout"] == 8.0
    assert captured["max_retries"] == 0
