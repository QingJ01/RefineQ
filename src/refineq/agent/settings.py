"""Persisted OpenAI-compatible model configuration."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr

from refineq.storage.json_store import validate_identifier

MODEL_SETTINGS_SCHEMA_VERSION = 1


class ModelNotConfiguredError(RuntimeError):
    """Raised when chat is requested before a model is configured."""


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: HttpUrl = "https://api.openai.com/v1"
    model: str = Field(min_length=1, max_length=200)
    api_key: SecretStr = Field(min_length=1, max_length=500)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class PublicModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str
    model: str
    temperature: float
    configured: bool
    api_key_hint: str = ""


class ModelSettingsRepository:
    def __init__(self, data_root: Path) -> None:
        self._data_root = data_root.expanduser().resolve()
        self._lock = RLock()

    def _path(self, owner_id: str) -> Path:
        owner_id = validate_identifier(owner_id, field="owner_id")
        return self._data_root / "users" / owner_id / "settings" / "model.json"

    def save(self, owner_id: str, settings: ModelSettings) -> ModelSettings:
        document = {
            "schema_version": MODEL_SETTINGS_SCHEMA_VERSION,
            "base_url": str(settings.base_url),
            "model": settings.model,
            "api_key": settings.api_key.get_secret_value(),
            "temperature": settings.temperature,
        }
        payload = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode()
        path = self._path(owner_id)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".model-",
                suffix=".tmp",
                dir=path.parent,
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
        return settings

    def load(self, owner_id: str) -> ModelSettings:
        path = self._path(owner_id)
        with self._lock:
            if not path.exists():
                raise ModelNotConfiguredError("Model settings have not been configured")
            try:
                document = json.loads(path.read_text(encoding="utf-8"))
                if document.pop("schema_version") != MODEL_SETTINGS_SCHEMA_VERSION:
                    raise ValueError("unsupported model settings schema")
                return ModelSettings.model_validate(document)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
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
