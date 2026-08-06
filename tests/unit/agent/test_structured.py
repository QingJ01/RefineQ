"""Strict parsing contracts for structured model operations."""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict

from refineq.agent.structured import StructuredModelResponseError, parse_structured_reply


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

