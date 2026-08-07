"""Tests for importing the pre-SQL RefineQ data layout."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import func, select

from refineq.database.engine import Database
from refineq.database.schema import material_chunks, materials, records, system_settings, users
from refineq.integrations.models import IntegrationKind
from refineq.integrations.repository import IntegrationRepository
from refineq.operations.postgres_migration import LegacyDataMigrator


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _legacy_search_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """CREATE TABLE materials (
                project_id TEXT, material_id TEXT, filename TEXT, content_type TEXT,
                size INTEGER, status TEXT, chunk_count INTEGER,
                content_sha256 TEXT, indexed_at TEXT
            )"""
        )
        connection.execute(
            """CREATE TABLE material_chunks (
                project_id TEXT, material_id TEXT, filename TEXT,
                chunk_index INTEGER, content TEXT
            )"""
        )
        connection.execute(
            "INSERT INTO materials VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "math",
                "notes",
                "notes.txt",
                "text/plain",
                12,
                "indexed",
                1,
                "a" * 64,
                "2026-08-01T00:00:00+00:00",
            ),
        )
        connection.execute(
            "INSERT INTO material_chunks VALUES (?, ?, ?, ?, ?)",
            ("math", "notes", "notes.txt", 0, "The chain rule."),
        )


def test_legacy_migration_is_idempotent_and_preserves_source_files(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    auth_path = root / "system" / "auth.json"
    _write_json(
        auth_path,
        {
            "schema_version": 1,
            "signing_secret": "legacy-signing-secret",
            "users": {
                "learner@example.com": {
                    "id": "user_legacy",
                    "email": "learner@example.com",
                    "display_name": "Legacy Learner",
                    "password_hash": "$2b$12$abcdefghijklmnopqrstuuuuuuuuuuuuuuuuuuuuuuuuuuuuu",
                    "created_at": "2026-08-01T00:00:00+00:00",
                }
            },
        },
    )
    record_path = root / "users" / "user_legacy" / "workspaces" / "math.json"
    _write_json(
        record_path,
        {"schema_version": 1, "version": 3, "data": {"id": "math", "title": "Calculus"}},
    )
    search_path = root / "users" / "user_legacy" / "knowledge" / "search.sqlite3"
    _legacy_search_database(search_path)

    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'target.sqlite3').as_posix()}")
    database.initialize()
    migrator = LegacyDataMigrator(root, database)

    first = migrator.migrate()
    second = migrator.migrate()

    assert first.imported_users == 1
    assert first.imported_records == 1
    assert first.imported_materials == 1
    assert first.imported_chunks == 1
    assert second.imported_total == 0
    assert second.skipped_total == 3
    assert auth_path.is_file()
    assert record_path.is_file()
    assert search_path.is_file()
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(users)) == 1
        assert session.scalar(select(func.count()).select_from(records)) == 1
        assert session.scalar(select(func.count()).select_from(materials)) == 1
        assert session.scalar(select(func.count()).select_from(material_chunks)) == 1
        assert (
            session.scalar(
                select(system_settings.c.value).where(system_settings.c.key == "jwt_signing_secret")
            )
            == "legacy-signing-secret"
        )


def test_dry_run_reports_without_writing(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    _write_json(
        root / "users" / "user_legacy" / "learning" / "math.json",
        {"schema_version": 1, "version": 1, "data": {"id": "math"}},
    )
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'target.sqlite3').as_posix()}")
    database.initialize()

    report = LegacyDataMigrator(root, database).migrate(dry_run=True)

    assert report.imported_records == 1
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(records)) == 0


def test_personal_model_config_requires_explicit_owner_before_platform_import(
    tmp_path: Path,
) -> None:
    root = tmp_path / "legacy"
    legacy_key = Fernet.generate_key()
    (root / "system").mkdir(parents=True)
    (root / "system" / "model-encryption.key").write_bytes(legacy_key)
    _write_json(
        root / "system" / "auth.json",
        {
            "schema_version": 1,
            "signing_secret": "legacy-secret",
            "users": {
                "owner@example.com": {
                    "id": "user_owner",
                    "email": "owner@example.com",
                    "display_name": "Owner",
                    "password_hash": "$2b$12$abcdefghijklmnopqrstuuuuuuuuuuuuuuuuuuuuuuuuuuuuu",
                    "created_at": "2026-08-01T00:00:00+00:00",
                }
            },
        },
    )
    _write_json(
        root / "users" / "user_owner" / "settings" / "model.json",
        {
            "schema_version": 2,
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-test",
            "temperature": 0.1,
            "encrypted_api_key": Fernet(legacy_key).encrypt(b"sk-legacy").decode(),
        },
    )
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'target.sqlite3').as_posix()}")
    database.initialize()

    unselected = LegacyDataMigrator(root, database).migrate()
    selected = LegacyDataMigrator(
        root,
        database,
        platform_owner_email="owner@example.com",
    ).migrate()

    assert unselected.imported_integrations == 0
    assert any("platform-owner-email" in warning for warning in unselected.warnings)
    assert selected.imported_integrations == 1
    repository = IntegrationRepository(
        database,
        key_path=root / "system" / "integration-encryption.key",
    )
    settings = repository.load(IntegrationKind.CHAT)
    assert settings.config["model"] == "gpt-test"
    assert settings.secrets["api_key"].get_secret_value() == "sk-legacy"
