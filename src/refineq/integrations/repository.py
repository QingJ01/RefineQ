"""Encrypted PostgreSQL repository for platform-wide integrations."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from datetime import UTC
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr
from sqlalchemy import func, insert, select, update

from refineq.database.engine import Database
from refineq.database.schema import audit_logs, integration_settings, utc_now
from refineq.integrations.models import (
    SECRET_FIELDS,
    IntegrationKind,
    IntegrationSettings,
    IntegrationUpdate,
    PublicIntegrationSettings,
    default_config,
    validate_config,
)


class IntegrationNotConfiguredError(RuntimeError):
    """Raised when an enabled capability has not been configured."""


class IntegrationConfigurationError(RuntimeError):
    """Raised when persisted integration configuration cannot be used safely."""


class IntegrationRepository:
    def __init__(
        self,
        database: Database,
        *,
        encryption_key: SecretStr | str | bytes | None = None,
        key_path: Path | None = None,
        allowed_model_hosts: set[str] | None = None,
        allowed_object_storage_hosts: set[str] | None = None,
    ) -> None:
        self.database = database
        self._configured_key = encryption_key
        self._key_path = key_path
        self._allowed_model_hosts = (
            {host.lower().rstrip(".") for host in allowed_model_hosts}
            if allowed_model_hosts is not None
            else None
        )
        self._allowed_object_storage_hosts = (
            {host.lower().rstrip(".") for host in allowed_object_storage_hosts}
            if allowed_object_storage_hosts is not None
            else None
        )
        self._cipher: Fernet | None = None
        self._lock = RLock()

    def _get_cipher(self) -> Fernet:
        with self._lock:
            if self._cipher is None:
                configured = self._configured_key
                if isinstance(configured, SecretStr):
                    configured = configured.get_secret_value()
                if configured:
                    key = configured.encode("ascii") if isinstance(configured, str) else configured
                else:
                    path = self._key_path
                    if path is None:
                        raise RuntimeError("integration encryption key path is not configured")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.exists():
                        key = path.read_bytes().strip()
                    else:
                        key = Fernet.generate_key()
                        descriptor, temporary_name = tempfile.mkstemp(
                            prefix=".integration-key-",
                            suffix=".tmp",
                            dir=path.parent,
                        )
                        temporary = Path(temporary_name)
                        try:
                            with os.fdopen(descriptor, "wb") as output:
                                output.write(key)
                                output.flush()
                                os.fsync(output.fileno())
                            with suppress(OSError):
                                os.chmod(temporary, 0o600)
                            os.replace(temporary, path)
                        finally:
                            temporary.unlink(missing_ok=True)
                self._cipher = Fernet(key)
            return self._cipher

    def _encrypt(self, secrets: dict[str, str]) -> str:
        payload = json.dumps(secrets, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return self._get_cipher().encrypt(payload).decode("ascii")

    def _decrypt(self, payload: str) -> dict[str, SecretStr]:
        if not payload:
            return {}
        try:
            decoded = self._get_cipher().decrypt(payload.encode("ascii"))
            document = json.loads(decoded.decode("utf-8"))
            if not isinstance(document, dict):
                raise ValueError("invalid integration secret document")
            return {str(key): SecretStr(str(value)) for key, value in document.items()}
        except (InvalidToken, UnicodeError, ValueError, json.JSONDecodeError) as error:
            raise IntegrationConfigurationError("Integration secrets are invalid") from error

    def _row_to_settings(self, kind: IntegrationKind, row) -> IntegrationSettings:
        return IntegrationSettings(
            kind=kind,
            enabled=bool(row.enabled),
            config=dict(row.config),
            secrets=self._decrypt(row.encrypted_secrets),
        )

    def load(self, kind: IntegrationKind) -> IntegrationSettings:
        with self.database.session() as session:
            row = session.execute(
                select(integration_settings).where(integration_settings.c.kind == kind.value)
            ).one_or_none()
        if row is None:
            raise IntegrationNotConfiguredError(f"{kind.value} integration is not configured")
        return self._row_to_settings(kind, row)

    def save(
        self,
        kind: IntegrationKind,
        payload: IntegrationUpdate,
        *,
        actor_id: str,
    ) -> PublicIntegrationSettings:
        config = validate_config(kind, payload.config)
        allowed_hosts = (
            self._allowed_object_storage_hosts
            if kind is IntegrationKind.OBJECT_STORAGE
            else self._allowed_model_hosts
        )
        endpoint_key = "endpoint_url" if kind is IntegrationKind.OBJECT_STORAGE else "base_url"
        if allowed_hosts is not None:
            host = (urlsplit(str(config[endpoint_key])).hostname or "").lower().rstrip(".")
            if host not in allowed_hosts:
                raise ValueError(f"Integration endpoint host {host!r} is not in the allowlist")
        unknown = set(payload.secrets) - SECRET_FIELDS[kind]
        if unknown:
            raise ValueError(f"Unsupported secret fields: {', '.join(sorted(unknown))}")

        with self._lock:
            try:
                existing = self.load(kind)
                secrets = {
                    name: value.get_secret_value() for name, value in existing.secrets.items()
                }
            except IntegrationNotConfiguredError:
                secrets = {}
            secrets.update(
                {
                    name: value.get_secret_value()
                    for name, value in payload.secrets.items()
                    if value.get_secret_value()
                }
            )
            if payload.enabled and not SECRET_FIELDS[kind] <= set(secrets):
                raise ValueError(f"{kind.value} credentials are required before enabling it")

            now = utc_now()
            encrypted = self._encrypt(secrets)
            with self.database.session() as session:
                exists = session.scalar(
                    select(func.count())
                    .select_from(integration_settings)
                    .where(integration_settings.c.kind == kind.value)
                )
                values = {
                    "enabled": payload.enabled,
                    "config": config,
                    "encrypted_secrets": encrypted,
                    "updated_by": actor_id,
                    "updated_at": now,
                }
                if exists:
                    session.execute(
                        update(integration_settings)
                        .where(integration_settings.c.kind == kind.value)
                        .values(**values)
                    )
                else:
                    session.execute(insert(integration_settings).values(kind=kind.value, **values))
                session.execute(
                    insert(audit_logs).values(
                        actor_id=actor_id,
                        action="integration.updated",
                        target=kind.value,
                        details={"enabled": payload.enabled, "config_fields": sorted(config)},
                        created_at=now,
                    )
                )
        return self.public(kind)

    def public(self, kind: IntegrationKind) -> PublicIntegrationSettings:
        with self.database.session() as session:
            row = session.execute(
                select(integration_settings).where(integration_settings.c.kind == kind.value)
            ).one_or_none()
        if row is None:
            return PublicIntegrationSettings(
                kind=kind,
                enabled=False,
                configured=False,
                config=default_config(kind),
            )
        secrets = self._decrypt(row.encrypted_secrets)
        configured = SECRET_FIELDS[kind] <= set(secrets)
        return PublicIntegrationSettings(
            kind=kind,
            enabled=bool(row.enabled),
            configured=configured,
            config=dict(row.config),
            secret_hints={
                name: f"••••{value.get_secret_value()[-4:]}" for name, value in secrets.items()
            },
            last_test_status=row.last_test_status,
            last_test_message=row.last_test_message,
            last_tested_at=(
                row.last_tested_at.replace(tzinfo=UTC).isoformat()
                if row.last_tested_at and row.last_tested_at.tzinfo is None
                else row.last_tested_at.isoformat()
                if row.last_tested_at
                else None
            ),
        )

    def list_public(self) -> list[PublicIntegrationSettings]:
        return [self.public(kind) for kind in IntegrationKind]

    def count_configured(self) -> int:
        return sum(item.configured for item in self.list_public())

    def list_audit_logs(self, *, limit: int = 50) -> list[dict[str, object]]:
        with self.database.session() as session:
            rows = session.execute(
                select(audit_logs).order_by(audit_logs.c.created_at.desc()).limit(limit)
            ).all()
        return [
            {
                "id": row.id,
                "actor_id": row.actor_id,
                "action": row.action,
                "target": row.target,
                "details": dict(row.details),
                "created_at": row.created_at,
            }
            for row in rows
        ]

    def record_test(
        self,
        kind: IntegrationKind,
        *,
        status: str,
        message: str,
        actor_id: str,
    ) -> None:
        now = utc_now()
        with self.database.session() as session:
            session.execute(
                update(integration_settings)
                .where(integration_settings.c.kind == kind.value)
                .values(
                    last_test_status=status,
                    last_test_message=message[:500],
                    last_tested_at=now,
                )
            )
            session.execute(
                insert(audit_logs).values(
                    actor_id=actor_id,
                    action="integration.tested",
                    target=kind.value,
                    details={"status": status},
                    created_at=now,
                )
            )
