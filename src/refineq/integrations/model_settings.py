"""Adapter exposing the platform chat integration to existing Agent services."""

from __future__ import annotations

from refineq.agent.settings import (
    ModelEndpointNotAllowedError,
    ModelNotConfiguredError,
    ModelSettings,
    PublicModelSettings,
)
from refineq.integrations.models import IntegrationKind, IntegrationUpdate
from refineq.integrations.repository import (
    IntegrationNotConfiguredError,
    IntegrationRepository,
)


class PlatformModelSettingsRepository:
    def __init__(self, integrations: IntegrationRepository, *, allowed_hosts: set[str]) -> None:
        self.integrations = integrations
        self.allowed_hosts = allowed_hosts

    def _validate_host(self, settings: ModelSettings) -> None:
        host = (settings.base_url.host or "").lower().rstrip(".")
        if host not in self.allowed_hosts:
            raise ModelEndpointNotAllowedError(
                f"Model endpoint host {host!r} is not in the server allowlist"
            )

    def save(self, owner_id: str, settings: ModelSettings) -> ModelSettings:
        self._validate_host(settings)
        self.integrations.save(
            IntegrationKind.CHAT,
            IntegrationUpdate(
                enabled=True,
                config={
                    "base_url": str(settings.base_url),
                    "model": settings.model,
                    "temperature": settings.temperature,
                    "allow_private_network": settings.allow_private_network,
                },
                secrets={"api_key": settings.api_key},
            ),
            actor_id=owner_id,
        )
        return settings

    def load(self, owner_id: str) -> ModelSettings:
        del owner_id
        try:
            integration = self.integrations.load(IntegrationKind.CHAT)
        except IntegrationNotConfiguredError as error:
            raise ModelNotConfiguredError("Model settings have not been configured") from error
        if not integration.enabled or "api_key" not in integration.secrets:
            raise ModelNotConfiguredError("Model settings have not been configured")
        settings = ModelSettings(
            base_url=integration.config["base_url"],
            model=integration.config["model"],
            temperature=integration.config.get("temperature", 0.2),
            api_key=integration.secrets["api_key"],
            allow_private_network=bool(integration.config.get("allow_private_network", False)),
        )
        self._validate_host(settings)
        return settings

    def public(self, owner_id: str) -> PublicModelSettings:
        del owner_id
        try:
            settings = self.load("platform")
        except ModelNotConfiguredError:
            public = self.integrations.public(IntegrationKind.CHAT)
            return PublicModelSettings(
                base_url=str(public.config.get("base_url", "https://api.openai.com/v1")),
                model=str(public.config.get("model", "")),
                temperature=float(public.config.get("temperature", 0.2)),
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
