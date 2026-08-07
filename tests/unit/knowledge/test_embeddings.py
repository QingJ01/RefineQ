"""Tests for administrator-configured embedding providers."""

from __future__ import annotations

from types import SimpleNamespace

from pydantic import SecretStr

from refineq.database.schema import EMBEDDING_DIMENSIONS
from refineq.integrations.models import IntegrationKind, IntegrationSettings
from refineq.knowledge import embeddings as embeddings_module
from refineq.knowledge.embeddings import PlatformEmbeddingService


class _Repository:
    def load(self, kind: IntegrationKind) -> IntegrationSettings:
        assert kind is IntegrationKind.EMBEDDING
        return IntegrationSettings(
            kind=kind,
            enabled=True,
            config={
                "base_url": "https://api.siliconflow.cn/v1",
                "model": "BAAI/bge-m3",
                "dimensions": 1024,
                "allow_private_network": False,
            },
            secrets={"api_key": SecretStr("embedding-secret")},
        )


def test_native_1024_vectors_are_zero_padded_for_pgvector(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Embeddings:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                data=[SimpleNamespace(index=0, embedding=[0.25] * 1024)],
            )

    monkeypatch.setattr(
        embeddings_module,
        "OpenAI",
        lambda **_: SimpleNamespace(embeddings=_Embeddings()),
    )

    vectors = PlatformEmbeddingService(_Repository()).embed(["学习资料"])

    assert "dimensions" not in captured
    assert len(vectors[0]) == EMBEDDING_DIMENSIONS
    assert vectors[0][:1024] == [0.25] * 1024
    assert vectors[0][1024:] == [0.0] * (EMBEDDING_DIMENSIONS - 1024)
