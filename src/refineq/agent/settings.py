"""OpenAI-compatible model configuration and its consumer-facing interface."""

from __future__ import annotations

from ipaddress import ip_address
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, SecretStr, model_validator


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


class ModelSettingsRepository(Protocol):
    """Structural boundary required by model-consuming services."""

    def load(self, owner_id: str) -> ModelSettings:
        """Load effective settings or raise ModelNotConfiguredError."""
        ...
