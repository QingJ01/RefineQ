"""Safe live checks for administrator-managed integrations."""

from __future__ import annotations

from openai import OpenAI

from refineq.integrations.models import IntegrationKind, IntegrationTestResult
from refineq.integrations.object_storage import S3ObjectStorage
from refineq.integrations.repository import IntegrationRepository


class IntegrationTester:
    def __init__(self, repository: IntegrationRepository) -> None:
        self.repository = repository

    def test(self, kind: IntegrationKind, *, actor_id: str) -> IntegrationTestResult:
        integration = self.repository.load(kind)
        secrets = {name: value.get_secret_value() for name, value in integration.secrets.items()}
        try:
            if kind is IntegrationKind.CHAT:
                client = OpenAI(
                    api_key=secrets["api_key"],
                    base_url=str(integration.config["base_url"]),
                    timeout=15.0,
                )
                client.chat.completions.create(
                    model=str(integration.config["model"]),
                    messages=[{"role": "user", "content": "Reply OK"}],
                    max_tokens=2,
                )
            elif kind is IntegrationKind.EMBEDDING:
                client = OpenAI(
                    api_key=secrets["api_key"],
                    base_url=str(integration.config["base_url"]),
                    timeout=15.0,
                )
                client.embeddings.create(
                    model=str(integration.config["model"]),
                    input=["RefineQ connection test"],
                    dimensions=int(integration.config["dimensions"]),
                )
            elif kind is IntegrationKind.OCR:
                client = OpenAI(
                    api_key=secrets["api_key"],
                    base_url=str(integration.config["base_url"]),
                    timeout=15.0,
                )
                client.models.retrieve(str(integration.config["model"]))
            else:
                S3ObjectStorage(integration).test_connection()
        except Exception as error:
            message = self._sanitize(str(error), secrets)
            self.repository.record_test(
                kind,
                status="failed",
                message=message,
                actor_id=actor_id,
            )
            return IntegrationTestResult(kind=kind, status="failed", message=message)

        message = "Connection succeeded"
        self.repository.record_test(kind, status="ok", message=message, actor_id=actor_id)
        return IntegrationTestResult(kind=kind, status="ok", message=message)

    @staticmethod
    def _sanitize(message: str, secrets: dict[str, str]) -> str:
        sanitized = message
        for secret in secrets.values():
            if secret:
                sanitized = sanitized.replace(secret, "[redacted]")
        return sanitized[:500] or "Connection failed"
