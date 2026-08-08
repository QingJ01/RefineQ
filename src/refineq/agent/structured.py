"""Schema-validated JSON operations over OpenAI-compatible chat models."""

from __future__ import annotations

import json
import re
from typing import Protocol, TypeVar

from openai import DefaultHttpxClient, OpenAI
from pydantic import BaseModel, ValidationError

from refineq.agent.settings import ModelSettings
from refineq.integrations.endpoints import assert_safe_endpoint

StructuredResponse = TypeVar("StructuredResponse", bound=BaseModel)


class StructuredModelResponseError(RuntimeError):
    """Raised when a model response cannot satisfy the required schema."""


def parse_structured_reply(
    text: str,
    response_model: type[StructuredResponse],
) -> StructuredResponse:
    """Extract the first JSON object and validate it without accepting extra fields."""

    candidate = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", candidate, flags=re.DOTALL)
    if fenced:
        candidate = fenced.group(1).strip()
    decoder = json.JSONDecoder()
    for index, character in enumerate(candidate):
        if character != "{":
            continue
        try:
            document, _ = decoder.raw_decode(candidate[index:])
            return response_model.model_validate(document)
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
            continue
    raise StructuredModelResponseError("Model did not return valid structured JSON")


class StructuredModelTransport(Protocol):
    def complete(
        self,
        *,
        settings: ModelSettings,
        messages: list[dict[str, str]],
        response_model: type[StructuredResponse],
    ) -> StructuredResponse: ...


class OpenAICompatibleStructuredTransport:
    def __init__(self, *, timeout: float = 30.0, max_retries: int = 2) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self._timeout = timeout
        self._max_retries = max_retries

    def complete(
        self,
        *,
        settings: ModelSettings,
        messages: list[dict[str, str]],
        response_model: type[StructuredResponse],
    ) -> StructuredResponse:
        assert_safe_endpoint(
            str(settings.base_url),
            allow_private_network=settings.allow_private_network,
            allow_transparent_proxy=True,
        )
        client = OpenAI(
            api_key=settings.api_key.get_secret_value(),
            base_url=str(settings.base_url),
            timeout=self._timeout,
            max_retries=self._max_retries,
            http_client=DefaultHttpxClient(follow_redirects=False),
        )
        response = client.chat.completions.create(
            model=settings.model,
            messages=messages,
            temperature=settings.temperature,
            response_format={"type": "json_object"},
            max_tokens=4_000,
        )
        return parse_structured_reply(
            response.choices[0].message.content or "",
            response_model,
        )
