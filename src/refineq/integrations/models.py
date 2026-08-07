"""Typed integration configuration and redacted API models."""

from __future__ import annotations

from enum import StrEnum
from ipaddress import ip_address
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SecretStr,
    field_validator,
    model_validator,
)


class IntegrationKind(StrEnum):
    CHAT = "chat"
    EMBEDDING = "embedding"
    OCR = "ocr"
    OBJECT_STORAGE = "object_storage"


class SecureEndpointConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow_private_network: bool = False

    @staticmethod
    def validate_endpoint(value: HttpUrl) -> HttpUrl:
        if value.scheme != "https" or value.username or value.password or value.fragment:
            raise ValueError("integration endpoint must be a credential-free HTTPS URL")
        return value

    @model_validator(mode="after")
    def validate_literal_endpoint(self) -> SecureEndpointConfig:
        endpoint = getattr(self, "base_url", None) or getattr(self, "endpoint_url", None)
        host = (endpoint.host or "").strip("[]")
        try:
            address = ip_address(host)
        except ValueError:
            return self
        if not address.is_global and not self.allow_private_network:
            raise ValueError("integration endpoint must not target a non-public IP address")
        return self


class ChatConfig(SecureEndpointConfig):
    base_url: HttpUrl = "https://api.openai.com/v1"
    model: str = Field(min_length=1, max_length=200)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    _secure_url = field_validator("base_url")(SecureEndpointConfig.validate_endpoint)


class EmbeddingConfig(SecureEndpointConfig):
    base_url: HttpUrl = "https://api.openai.com/v1"
    model: str = Field(min_length=1, max_length=200)
    dimensions: Literal[1536] = 1536

    _secure_url = field_validator("base_url")(SecureEndpointConfig.validate_endpoint)


class OcrConfig(SecureEndpointConfig):
    base_url: HttpUrl = "https://api.openai.com/v1"
    model: str = Field(min_length=1, max_length=200)

    _secure_url = field_validator("base_url")(SecureEndpointConfig.validate_endpoint)


class ObjectStorageConfig(SecureEndpointConfig):
    endpoint_url: HttpUrl
    bucket: str = Field(min_length=3, max_length=255)
    region: str = Field(default="auto", min_length=1, max_length=100)
    addressing_style: Literal["auto", "path", "virtual"] = "auto"

    _secure_url = field_validator("endpoint_url")(SecureEndpointConfig.validate_endpoint)

    @field_validator("bucket", mode="after")
    @classmethod
    def validate_bucket(cls, value: str) -> str:
        normalized = value.strip()
        if normalized != value or any(character.isspace() for character in value):
            raise ValueError("bucket must not contain whitespace")
        return value


CONFIG_MODELS = {
    IntegrationKind.CHAT: ChatConfig,
    IntegrationKind.EMBEDDING: EmbeddingConfig,
    IntegrationKind.OCR: OcrConfig,
    IntegrationKind.OBJECT_STORAGE: ObjectStorageConfig,
}

SECRET_FIELDS = {
    IntegrationKind.CHAT: {"api_key"},
    IntegrationKind.EMBEDDING: {"api_key"},
    IntegrationKind.OCR: {"api_key"},
    IntegrationKind.OBJECT_STORAGE: {"access_key_id", "secret_access_key"},
}


def default_config(kind: IntegrationKind) -> dict[str, object]:
    defaults: dict[IntegrationKind, dict[str, object]] = {
        IntegrationKind.CHAT: {
            "base_url": "https://api.openai.com/v1",
            "model": "",
            "temperature": 0.2,
            "allow_private_network": False,
        },
        IntegrationKind.EMBEDDING: {
            "base_url": "https://api.openai.com/v1",
            "model": "text-embedding-3-small",
            "dimensions": 1536,
            "allow_private_network": False,
        },
        IntegrationKind.OCR: {
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4.1-mini",
            "allow_private_network": False,
        },
        IntegrationKind.OBJECT_STORAGE: {
            "endpoint_url": "",
            "bucket": "",
            "region": "auto",
            "addressing_style": "auto",
            "allow_private_network": False,
        },
    }
    return dict(defaults[kind])


class IntegrationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    config: dict[str, object]
    secrets: dict[str, SecretStr] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_blank_secret_names(self) -> IntegrationUpdate:
        if any(not key.strip() for key in self.secrets):
            raise ValueError("secret names must not be blank")
        return self


class IntegrationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: IntegrationKind
    enabled: bool
    config: dict[str, object]
    secrets: dict[str, SecretStr]


class PublicIntegrationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: IntegrationKind
    enabled: bool
    configured: bool
    config: dict[str, object]
    secret_hints: dict[str, str] = Field(default_factory=dict)
    last_test_status: str | None = None
    last_test_message: str | None = None
    last_tested_at: str | None = None


class IntegrationTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: IntegrationKind
    status: Literal["ok", "failed"]
    message: str


def validate_config(kind: IntegrationKind, config: dict[str, object]) -> dict[str, object]:
    model = CONFIG_MODELS[kind]
    return model.model_validate(config).model_dump(mode="json")
