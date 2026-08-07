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


def test_default_model_allowlist_includes_supported_public_providers(monkeypatch) -> None:
    monkeypatch.delenv("REFINEQ_MODEL_ENDPOINT_ALLOWED_HOSTS", raising=False)

    settings = Settings(_env_file=None)

    assert {
        "api.openai.com",
        "api.deepseek.com",
        "api.siliconflow.cn",
    } <= settings.allowed_model_hosts


def test_model_encryption_key_is_validated_at_startup(monkeypatch) -> None:
    monkeypatch.setenv("REFINEQ_MODEL_ENCRYPTION_KEY", "not-a-fernet-key")

    with pytest.raises(ValidationError, match="valid Fernet key"):
        Settings(_env_file=None)


def test_upload_concurrency_limits_are_configurable_and_positive(monkeypatch) -> None:
    monkeypatch.setenv("REFINEQ_MATERIAL_UPLOAD_MAX_CONCURRENT_GLOBAL", "6")
    monkeypatch.setenv("REFINEQ_MATERIAL_UPLOAD_MAX_CONCURRENT_PER_USER", "3")
    monkeypatch.setenv("REFINEQ_MATERIAL_UPLOAD_BODY_IDLE_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("REFINEQ_MATERIAL_UPLOAD_BODY_TOTAL_TIMEOUT_SECONDS", "90")

    settings = Settings(_env_file=None)

    assert settings.material_upload_max_concurrent_global == 6
    assert settings.material_upload_max_concurrent_per_user == 3
    assert settings.material_upload_body_idle_timeout_seconds == 12
    assert settings.material_upload_body_total_timeout_seconds == 90

    monkeypatch.setenv("REFINEQ_MATERIAL_UPLOAD_MAX_CONCURRENT_PER_USER", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_database_url_defaults_to_owner_local_sqlite_for_development(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "runtime", _env_file=None)

    assert settings.resolved_database_url == (
        f"sqlite+pysqlite:///{(tmp_path / 'runtime' / 'system' / 'refineq.sqlite3').as_posix()}"
    )


def test_database_url_accepts_postgresql_psycopg_and_rejects_unknown_drivers(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "REFINEQ_DATABASE_URL",
        "postgresql+psycopg://refineq:secret@database:5432/refineq",
    )

    settings = Settings(_env_file=None)

    assert settings.resolved_database_url.startswith("postgresql+psycopg://")

    monkeypatch.setenv("REFINEQ_DATABASE_URL", "mysql://root@database/refineq")
    with pytest.raises(ValidationError, match="PostgreSQL or SQLite"):
        Settings(_env_file=None)
