"""Tests for the RefineQ runtime configuration boundary."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from refineq.config import Settings


def test_settings_resolve_refineq_data_root(monkeypatch, tmp_path: Path) -> None:
    configured_root = tmp_path / "runtime-data"
    monkeypatch.setenv("REFINEQ_DATA_ROOT", str(configured_root))

    settings = Settings(_env_file=None)

    assert settings.data_root == configured_root.resolve()


def test_server_defaults_are_loopback_safe(monkeypatch) -> None:
    monkeypatch.delenv("REFINEQ_HOST", raising=False)
    monkeypatch.delenv("REFINEQ_PORT", raising=False)

    settings = Settings(_env_file=None)

    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_model_encryption_key_is_validated_at_startup(monkeypatch) -> None:
    monkeypatch.setenv("REFINEQ_MODEL_ENCRYPTION_KEY", "not-a-fernet-key")

    with pytest.raises(ValidationError, match="valid Fernet key"):
        Settings(_env_file=None)
