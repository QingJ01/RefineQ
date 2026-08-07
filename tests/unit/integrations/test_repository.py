"""Encrypted platform integration repository tests."""

from __future__ import annotations

from refineq.database.engine import Database
from refineq.identity.service import IdentityService
from refineq.integrations.models import IntegrationKind, IntegrationUpdate
from refineq.integrations.repository import IntegrationRepository
from refineq.operations.admin import ensure_admin


def _repository(tmp_path) -> tuple[IntegrationRepository, str]:
    path = tmp_path / "integrations.sqlite3"
    database = Database(f"sqlite+pysqlite:///{path.as_posix()}")
    database.initialize()
    admin = ensure_admin(
        IdentityService(database),
        email="admin@example.com",
        password="correct-horse-battery-staple",
        display_name="Admin",
    ).user
    repository = IntegrationRepository(database, key_path=tmp_path / "integration.key")
    return repository, admin.id


def test_secrets_are_encrypted_and_public_views_are_redacted(tmp_path) -> None:
    repository, admin_id = _repository(tmp_path)

    repository.save(
        IntegrationKind.CHAT,
        IntegrationUpdate(
            enabled=True,
            config={
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4.1-mini",
                "temperature": 0.2,
            },
            secrets={"api_key": "sk-super-secret-1234"},
        ),
        actor_id=admin_id,
    )

    internal = repository.load(IntegrationKind.CHAT)
    public = repository.public(IntegrationKind.CHAT)
    assert internal.secrets["api_key"].get_secret_value() == "sk-super-secret-1234"
    assert public.configured is True
    assert public.secret_hints == {"api_key": "••••1234"}
    assert "sk-super-secret-1234" not in public.model_dump_json()
    assert "sk-super-secret-1234" not in (tmp_path / "integrations.sqlite3").read_bytes().decode(
        "utf-8", errors="ignore"
    )


def test_blank_secret_updates_preserve_existing_credentials(tmp_path) -> None:
    repository, admin_id = _repository(tmp_path)
    repository.save(
        IntegrationKind.EMBEDDING,
        IntegrationUpdate(
            enabled=True,
            config={
                "base_url": "https://api.openai.com/v1",
                "model": "text-embedding-3-small",
                "dimensions": 1536,
            },
            secrets={"api_key": "embedding-secret"},
        ),
        actor_id=admin_id,
    )

    repository.save(
        IntegrationKind.EMBEDDING,
        IntegrationUpdate(
            enabled=False,
            config={
                "base_url": "https://api.openai.com/v1",
                "model": "text-embedding-3-small",
                "dimensions": 1536,
            },
            secrets={},
        ),
        actor_id=admin_id,
    )

    loaded = repository.load(IntegrationKind.EMBEDDING)
    assert loaded.enabled is False
    assert loaded.secrets["api_key"].get_secret_value() == "embedding-secret"


def test_every_configuration_change_creates_a_secret_free_audit_entry(tmp_path) -> None:
    repository, admin_id = _repository(tmp_path)

    repository.save(
        IntegrationKind.OCR,
        IntegrationUpdate(
            enabled=True,
            config={
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4.1-mini",
            },
            secrets={"api_key": "ocr-secret"},
        ),
        actor_id=admin_id,
    )

    audits = repository.list_audit_logs()
    assert audits[0]["action"] == "integration.updated"
    assert audits[0]["target"] == "ocr"
    assert "secret" not in str(audits[0]["details"]).lower()
