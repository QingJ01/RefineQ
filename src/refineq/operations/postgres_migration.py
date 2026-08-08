"""Non-destructive import from the original JSON and owner-local SQLite layout."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr
from sqlalchemy import insert, or_, select

from refineq.database.engine import Database
from refineq.database.schema import (
    integration_settings,
    material_chunks,
    materials,
    records,
    system_settings,
    users,
)
from refineq.integrations.models import IntegrationKind, IntegrationUpdate, validate_config
from refineq.integrations.repository import IntegrationRepository
from refineq.storage.json_store import InvalidIdentifierError, validate_identifier

_AUTH_SECRET_KEY = "jwt_signing_secret"
_IGNORED_COLLECTIONS = {"knowledge", "settings", ".transactions"}


@dataclass(frozen=True, slots=True)
class MigrationReport:
    imported_users: int = 0
    imported_records: int = 0
    imported_materials: int = 0
    imported_chunks: int = 0
    imported_integrations: int = 0
    skipped_users: int = 0
    skipped_records: int = 0
    skipped_materials: int = 0
    skipped_integrations: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)
    dry_run: bool = False

    @property
    def imported_total(self) -> int:
        return (
            self.imported_users
            + self.imported_records
            + self.imported_materials
            + self.imported_integrations
        )

    @property
    def skipped_total(self) -> int:
        return (
            self.skipped_users
            + self.skipped_records
            + self.skipped_materials
            + self.skipped_integrations
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "dry_run": self.dry_run,
            "imported": {
                "users": self.imported_users,
                "records": self.imported_records,
                "materials": self.imported_materials,
                "chunks": self.imported_chunks,
                "integrations": self.imported_integrations,
            },
            "skipped_existing": {
                "users": self.skipped_users,
                "records": self.skipped_records,
                "materials": self.skipped_materials,
                "integrations": self.skipped_integrations,
            },
            "warnings": list(self.warnings),
        }


class LegacyDataMigrator:
    """Copy legacy data into SQL while leaving every source file untouched."""

    def __init__(
        self,
        data_root: Path,
        database: Database,
        *,
        platform_owner_email: str | None = None,
        integration_encryption_key: SecretStr | str | bytes | None = None,
        allowed_model_hosts: set[str] | None = None,
    ) -> None:
        self.data_root = data_root.expanduser().resolve()
        self.database = database
        self.platform_owner_email = (
            platform_owner_email.strip().lower() if platform_owner_email else None
        )
        self.integration_encryption_key = integration_encryption_key
        self.allowed_model_hosts = allowed_model_hosts

    @staticmethod
    def _timestamp(value: Any) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return datetime.now(UTC)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _load_auth(self, warnings: list[str]) -> dict[str, Any] | None:
        path = self.data_root / "system" / "auth.json"
        if not path.is_file():
            return None
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            if (
                document.get("schema_version") != 1
                or not isinstance(document.get("users"), dict)
                or not isinstance(document.get("signing_secret"), str)
            ):
                raise ValueError("unsupported identity document")
            return document
        except (OSError, ValueError, json.JSONDecodeError) as error:
            warnings.append(f"Skipped invalid identity file {path}: {error}")
            return None

    def _import_auth(
        self,
        *,
        dry_run: bool,
        warnings: list[str],
    ) -> tuple[int, int]:
        document = self._load_auth(warnings)
        if document is None:
            return 0, 0
        imported = 0
        skipped = 0
        with self.database.session() as session:
            current_secret = session.scalar(
                select(system_settings.c.value).where(system_settings.c.key == _AUTH_SECRET_KEY)
            )
            if current_secret is None and not dry_run:
                session.execute(
                    insert(system_settings).values(
                        key=_AUTH_SECRET_KEY,
                        value=document["signing_secret"],
                        updated_at=datetime.now(UTC),
                    )
                )
            for raw in document["users"].values():
                if not isinstance(raw, dict):
                    warnings.append("Skipped a malformed legacy user entry")
                    continue
                try:
                    user_id = validate_identifier(str(raw["id"]), field="owner_id")
                    email = str(raw["email"]).strip().lower()
                    display_name = str(raw["display_name"]).strip()
                    password_hash = str(raw["password_hash"])
                    created_at = self._timestamp(raw["created_at"])
                    if not email or not display_name or not password_hash:
                        raise ValueError("required field is blank")
                except (KeyError, ValueError, InvalidIdentifierError) as error:
                    warnings.append(f"Skipped malformed legacy user: {error}")
                    continue
                exists = session.scalar(
                    select(users.c.id).where(or_(users.c.id == user_id, users.c.email == email))
                )
                if exists is not None:
                    skipped += 1
                    continue
                imported += 1
                if not dry_run:
                    session.execute(
                        insert(users).values(
                            id=user_id,
                            email=email,
                            display_name=display_name,
                            password_hash=password_hash,
                            role="learner",
                            created_at=created_at,
                            updated_at=created_at,
                        )
                    )
        return imported, skipped

    def _record_files(self) -> list[tuple[str, str, Path]]:
        users_root = self.data_root / "users"
        if not users_root.is_dir():
            return []
        discovered: list[tuple[str, str, Path]] = []
        for owner_root in sorted(path for path in users_root.iterdir() if path.is_dir()):
            for collection_root in sorted(path for path in owner_root.iterdir() if path.is_dir()):
                if collection_root.name in _IGNORED_COLLECTIONS or collection_root.name.startswith(
                    "."
                ):
                    continue
                for record_path in sorted(collection_root.glob("*.json")):
                    discovered.append((owner_root.name, collection_root.name, record_path))
        return discovered

    def _import_records(
        self,
        *,
        dry_run: bool,
        warnings: list[str],
    ) -> tuple[int, int]:
        imported = 0
        skipped = 0
        with self.database.session() as session:
            for owner_id, collection, path in self._record_files():
                try:
                    owner_id = validate_identifier(owner_id, field="owner_id")
                    collection = validate_identifier(collection, field="collection")
                    record_id = validate_identifier(path.stem, field="record_id")
                    envelope = json.loads(path.read_text(encoding="utf-8"))
                    schema_version = int(envelope["schema_version"])
                    version = int(envelope["version"])
                    data = envelope["data"]
                    if schema_version < 1 or version < 1 or not isinstance(data, dict):
                        raise ValueError("invalid record envelope")
                except (
                    OSError,
                    KeyError,
                    TypeError,
                    ValueError,
                    json.JSONDecodeError,
                    InvalidIdentifierError,
                ) as error:
                    warnings.append(f"Skipped invalid record {path}: {error}")
                    continue
                exists = session.scalar(
                    select(records.c.record_id).where(
                        records.c.owner_id == owner_id,
                        records.c.collection == collection,
                        records.c.record_id == record_id,
                    )
                )
                if exists is not None:
                    skipped += 1
                    continue
                imported += 1
                if not dry_run:
                    session.execute(
                        insert(records).values(
                            owner_id=owner_id,
                            collection=collection,
                            record_id=record_id,
                            schema_version=schema_version,
                            version=version,
                            data=data,
                            updated_at=datetime.fromtimestamp(path.stat().st_mtime, UTC),
                        )
                    )
        return imported, skipped

    @staticmethod
    def _legacy_connection(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _import_materials(
        self,
        *,
        dry_run: bool,
        warnings: list[str],
    ) -> tuple[int, int, int]:
        imported = 0
        skipped = 0
        imported_chunks = 0
        users_root = self.data_root / "users"
        if not users_root.is_dir():
            return imported, skipped, imported_chunks
        with self.database.session() as session:
            for path in sorted(users_root.glob("*/knowledge/search.sqlite3")):
                owner_id = path.parent.parent.name
                try:
                    owner_id = validate_identifier(owner_id, field="owner_id")
                    with self._legacy_connection(path) as source:
                        source_materials = source.execute(
                            "SELECT * FROM materials ORDER BY project_id, material_id"
                        ).fetchall()
                        for material in source_materials:
                            project_id = validate_identifier(
                                material["project_id"], field="project_id"
                            )
                            material_id = validate_identifier(
                                material["material_id"], field="material_id"
                            )
                            exists = session.scalar(
                                select(materials.c.material_id).where(
                                    materials.c.owner_id == owner_id,
                                    materials.c.project_id == project_id,
                                    materials.c.material_id == material_id,
                                )
                            )
                            if exists is not None:
                                skipped += 1
                                continue
                            chunks = source.execute(
                                """SELECT filename, chunk_index, content
                                   FROM material_chunks
                                   WHERE project_id = ? AND material_id = ?
                                   ORDER BY CAST(chunk_index AS INTEGER)""",
                                (project_id, material_id),
                            ).fetchall()
                            imported += 1
                            imported_chunks += len(chunks)
                            if dry_run:
                                continue
                            session.execute(
                                insert(materials).values(
                                    owner_id=owner_id,
                                    project_id=project_id,
                                    material_id=material_id,
                                    filename=material["filename"],
                                    title=material["filename"],
                                    tags=[],
                                    content_type=material["content_type"],
                                    size=int(material["size"]),
                                    status=material["status"],
                                    chunk_count=len(chunks),
                                    content_sha256=material["content_sha256"],
                                    storage_key=None,
                                    indexed_at=self._timestamp(material["indexed_at"]),
                                )
                            )
                            if chunks:
                                session.execute(
                                    insert(material_chunks),
                                    [
                                        {
                                            "owner_id": owner_id,
                                            "project_id": project_id,
                                            "material_id": material_id,
                                            "filename": chunk["filename"],
                                            "chunk_index": int(chunk["chunk_index"]),
                                            "content": chunk["content"],
                                            "embedding": None,
                                        }
                                        for chunk in chunks
                                    ],
                                )
                except (
                    sqlite3.Error,
                    KeyError,
                    TypeError,
                    ValueError,
                    InvalidIdentifierError,
                ) as error:
                    warnings.append(f"Skipped invalid legacy search index {path}: {error}")
        return imported, skipped, imported_chunks

    def _import_platform_chat(
        self,
        *,
        dry_run: bool,
        warnings: list[str],
    ) -> tuple[int, int]:
        config_paths = sorted(self.data_root.glob("users/*/settings/model.json"))
        if not config_paths:
            return 0, 0
        if self.platform_owner_email is None:
            warnings.append(
                f"Found {len(config_paths)} personal model configuration(s); pass "
                "--platform-owner-email to explicitly select the platform configuration"
            )
            return 0, 0

        document = self._load_auth(warnings)
        legacy_user = (
            document.get("users", {}).get(self.platform_owner_email)
            if document is not None
            else None
        )
        if not isinstance(legacy_user, dict) or not legacy_user.get("id"):
            warnings.append(f"No legacy account matches platform owner {self.platform_owner_email}")
            return 0, 0
        owner_id = str(legacy_user["id"])
        path = self.data_root / "users" / owner_id / "settings" / "model.json"
        if not path.is_file():
            warnings.append(f"Selected platform owner has no model configuration: {path}")
            return 0, 0

        with self.database.session() as session:
            exists = session.scalar(
                select(integration_settings.c.kind).where(
                    integration_settings.c.kind == IntegrationKind.CHAT.value
                )
            )
            actor_exists = session.scalar(select(users.c.id).where(users.c.id == owner_id))
        if exists is not None:
            return 0, 1
        if actor_exists is None and not dry_run:
            warnings.append("Selected platform owner was not imported into the target database")
            return 0, 0

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            schema_version = int(raw["schema_version"])
            if schema_version == 1:
                api_key = str(raw["api_key"])
            elif schema_version == 2:
                legacy_key = (self.data_root / "system" / "model-encryption.key").read_bytes()
                api_key = (
                    Fernet(legacy_key.strip())
                    .decrypt(str(raw["encrypted_api_key"]).encode("ascii"))
                    .decode("utf-8")
                )
            else:
                raise ValueError("unsupported model settings schema")
            config = validate_config(
                IntegrationKind.CHAT,
                {
                    "base_url": raw["base_url"],
                    "model": raw["model"],
                    "temperature": raw.get("temperature", 0.2),
                },
            )
            payload = IntegrationUpdate(
                enabled=True,
                config=config,
                secrets={"api_key": SecretStr(api_key)},
            )
        except (
            OSError,
            KeyError,
            TypeError,
            ValueError,
            UnicodeError,
            InvalidToken,
            json.JSONDecodeError,
        ) as error:
            warnings.append(f"Skipped invalid personal model configuration {path}: {error}")
            return 0, 0

        if not dry_run:
            try:
                IntegrationRepository(
                    self.database,
                    encryption_key=self.integration_encryption_key,
                    key_path=self.data_root / "system" / "integration-encryption.key",
                    allowed_model_hosts=self.allowed_model_hosts,
                ).save(IntegrationKind.CHAT, payload, actor_id=owner_id)
            except ValueError as error:
                warnings.append(f"Skipped personal model configuration {path}: {error}")
                return 0, 0
        return 1, 0

    def migrate(self, *, dry_run: bool = False) -> MigrationReport:
        """Run an idempotent copy and return exact imported/skipped counts."""

        warnings: list[str] = []
        imported_users, skipped_users = self._import_auth(
            dry_run=dry_run,
            warnings=warnings,
        )
        imported_records, skipped_records = self._import_records(
            dry_run=dry_run,
            warnings=warnings,
        )
        imported_materials, skipped_materials, imported_chunks = self._import_materials(
            dry_run=dry_run,
            warnings=warnings,
        )
        imported_integrations, skipped_integrations = self._import_platform_chat(
            dry_run=dry_run,
            warnings=warnings,
        )
        return MigrationReport(
            imported_users=imported_users,
            imported_records=imported_records,
            imported_materials=imported_materials,
            imported_chunks=imported_chunks,
            imported_integrations=imported_integrations,
            skipped_users=skipped_users,
            skipped_records=skipped_records,
            skipped_materials=skipped_materials,
            skipped_integrations=skipped_integrations,
            warnings=tuple(warnings),
            dry_run=dry_run,
        )
