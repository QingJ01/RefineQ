"""OpenAI-compatible embedding provider managed by administrators."""

from __future__ import annotations

import math
from typing import Protocol

from openai import OpenAI

from refineq.integrations.models import IntegrationKind
from refineq.integrations.repository import (
    IntegrationNotConfiguredError,
    IntegrationRepository,
)


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class PlatformEmbeddingService:
    def __init__(self, integrations: IntegrationRepository) -> None:
        self.integrations = integrations

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        integration = self.integrations.load(IntegrationKind.EMBEDDING)
        if not integration.enabled or "api_key" not in integration.secrets:
            raise IntegrationNotConfiguredError("embedding integration is not enabled")
        dimensions = int(integration.config["dimensions"])
        client = OpenAI(
            api_key=integration.secrets["api_key"].get_secret_value(),
            base_url=str(integration.config["base_url"]),
            timeout=30.0,
        )
        response = client.embeddings.create(
            model=str(integration.config["model"]),
            input=texts,
            dimensions=dimensions,
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        vectors = [list(item.embedding) for item in ordered]
        if len(vectors) != len(texts):
            raise RuntimeError("Embedding provider returned an unexpected vector count")
        if any(
            len(vector) != dimensions or not all(math.isfinite(value) for value in vector)
            for vector in vectors
        ):
            raise RuntimeError("Embedding provider returned invalid vectors")
        return vectors
