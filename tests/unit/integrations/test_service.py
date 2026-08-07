"""Tests for safe live integration checks."""

from __future__ import annotations

from types import SimpleNamespace

from pydantic import SecretStr

from refineq.integrations import service as service_module
from refineq.integrations.models import IntegrationKind, IntegrationSettings
from refineq.integrations.service import IntegrationTester


class _Repository:
    def __init__(self) -> None:
        self.recorded: list[tuple[str, str]] = []

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

    def record_test(self, kind, *, status, message, actor_id) -> None:
        del kind, actor_id
        self.recorded.append((status, message))


def test_embedding_connection_check_omits_unsupported_dimensions_parameter(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Embeddings:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.1] * 1024)])

    monkeypatch.setattr(
        service_module,
        "OpenAI",
        lambda **_: SimpleNamespace(embeddings=_Embeddings()),
    )
    repository = _Repository()

    result = IntegrationTester(repository).test(
        IntegrationKind.EMBEDDING,
        actor_id="admin",
    )

    assert result.status == "ok"
    assert "dimensions" not in captured
    assert repository.recorded == [("ok", "Connection succeeded")]


def test_embedding_connection_check_rejects_an_unexpected_vector_dimension(monkeypatch) -> None:
    class _Embeddings:
        def create(self, **kwargs):
            del kwargs
            return SimpleNamespace(data=[SimpleNamespace(index=0, embedding=[0.1] * 512)])

    monkeypatch.setattr(
        service_module,
        "OpenAI",
        lambda **_: SimpleNamespace(embeddings=_Embeddings()),
    )
    repository = _Repository()

    result = IntegrationTester(repository).test(
        IntegrationKind.EMBEDDING,
        actor_id="admin",
    )

    assert result.status == "failed"
    assert "expected 1024" in result.message
    assert repository.recorded == [("failed", result.message)]
