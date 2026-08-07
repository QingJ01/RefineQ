"""Persisted and encrypted OpenAI-compatible model configuration."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import suppress
from ipaddress import ip_address
from pathlib import Path
from threading import RLock

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, model_validator

from refineq.storage.json_store import validate_identifier

MODEL_SETTINGS_SCHEMA_VERSION = 2


class ModelNotConfiguredError(RuntimeError):
    """Raised when chat is requested before a model is configured."""


class ModelEndpointNotAllowedError(ValueError):
    """Raised when a learner selects an endpoint the server did not approve."""


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: HttpUrl = "https://api.openai.com/v1"
    model: str = Field(min_length=1, max_length=200)
    api_key: SecretStr = Field(min_length=1, max_length=500)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    allow_private_network: bool = False

    @model_validator(mode="after")
    def validate_endpoint_shape(self) -> ModelSettings:
        if self.base_url.scheme != "https":
            raise ValueError("model base_url must use HTTPS")
        if self.base_url.username or self.base_url.password or self.base_url.fragment:
            raise ValueError("model base_url must not contain credentials or fragments")
        host = (self.base_url.host or "").strip("[]")
        try:
            address = ip_address(host)
        except ValueError:
            return self
        if not address.is_global and not self.allow_private_network:
            raise ValueError("model base_url must not target a non-public IP address")
        return self


class PublicModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str
    model: str
    temperature: float
    configured: bool
    api_key_hint: str = ""


class ModelSettingsRepository:
    def __init__(
        self,
        data_root: Path,
        *,
        allowed_hosts: set[str] | None = None,
        encryption_key: SecretStr | str | bytes | None = None,
    ) -> None:
        self._data_root = data_root.expanduser().resolve()
        self._allowed_hosts = {
            host.strip().lower().rstrip(".")
            for host in (allowed_hosts or {"api.openai.com"})
            if host.strip()
        }
        self._configured_encryption_key = encryption_key
        self._cipher: Fernet | None = None
        self._lock = RLock()

    def _get_cipher(self) -> Fernet:
        with self._lock:
            if self._cipher is None:
                self._cipher = Fernet(self._resolve_key(self._configured_encryption_key))
            return self._cipher

    def _resolve_key(self, configured: SecretStr | str | bytes | None) -> bytes:
        if isinstance(configured, SecretStr):
            configured = configured.get_secret_value()
        if configured:
            return configured.encode("ascii") if isinstance(configured, str) else configured

        path = self._data_root / "system" / "model-encryption.key"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return path.read_bytes().strip()

        key = Fernet.generate_key()
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".model-key-", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(key)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            with suppress(OSError):
                os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return key

    def _path(self, owner_id: str) -> Path:
        owner_id = validate_identifier(owner_id, field="owner_id")
        return self._data_root / "users" / owner_id / "settings" / "model.json"

    def _validate_allowed_endpoint(self, settings: ModelSettings) -> None:
        host = (settings.base_url.host or "").lower().rstrip(".")
        if host not in self._allowed_hosts:
            raise ModelEndpointNotAllowedError(
                f"Model endpoint host {host!r} is not in the server allowlist"
            )

    def _write(self, owner_id: str, document: dict[str, object]) -> None:
        payload = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode()
        path = self._path(owner_id)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".model-", suffix=".tmp", dir=path.parent
            )
            temporary_path = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as temporary_file:
                    temporary_file.write(payload)
                    temporary_file.flush()
                    os.fsync(temporary_file.fileno())
                os.replace(temporary_path, path)
            finally:
                temporary_path.unlink(missing_ok=True)

    def save(self, owner_id: str, settings: ModelSettings) -> ModelSettings:
        self._validate_allowed_endpoint(settings)
        self._write(
            owner_id,
            {
                "schema_version": MODEL_SETTINGS_SCHEMA_VERSION,
                "base_url": str(settings.base_url),
                "model": settings.model,
                "encrypted_api_key": self._get_cipher()
                .encrypt(settings.api_key.get_secret_value().encode("utf-8"))
                .decode("ascii"),
                "temperature": settings.temperature,
                "allow_private_network": settings.allow_private_network,
            },
        )
        return settings

    def load(self, owner_id: str) -> ModelSettings:
        path = self._path(owner_id)
        with self._lock:
            if not path.exists():
                raise ModelNotConfiguredError("Model settings have not been configured")
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                schema_version = document.pop("schema_version")
                if schema_version == 1:
                    settings = ModelSettings.model_validate(document)
                    self._validate_allowed_endpoint(settings)
                    self.save(owner_id, settings)
                    return settings
                if schema_version != MODEL_SETTINGS_SCHEMA_VERSION:
                    raise ValueError("unsupported model settings schema")
                encrypted_api_key = document.pop("encrypted_api_key")
                document["api_key"] = (
                    self._get_cipher().decrypt(encrypted_api_key.encode("ascii")).decode("utf-8")
                )
                settings = ModelSettings.model_validate(document)
                self._validate_allowed_endpoint(settings)
                return settings
            except (
                KeyError,
                TypeError,
                ValueError,
                UnicodeError,
                InvalidToken,
                json.JSONDecodeError,
            ) as error:
                raise ModelNotConfiguredError("Model settings are invalid") from error

    def public(self, owner_id: str) -> PublicModelSettings:
        try:
            settings = self.load(owner_id)
        except ModelNotConfiguredError:
            return PublicModelSettings(
                base_url="https://api.openai.com/v1",
                model="",
                temperature=0.2,
                configured=False,
            )
        secret = settings.api_key.get_secret_value()
        return PublicModelSettings(
            base_url=str(settings.base_url),
            model=settings.model,
            temperature=settings.temperature,
            configured=True,
            api_key_hint=f"••••{secret[-4:]}",
        )
