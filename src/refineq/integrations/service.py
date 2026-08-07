"""Safe live checks for administrator-managed integrations."""

from __future__ import annotations

import fitz
from openai import DefaultHttpxClient, OpenAI

from refineq.integrations.endpoints import assert_safe_endpoint
from refineq.integrations.models import IntegrationKind, IntegrationTestResult
from refineq.integrations.object_storage import S3ObjectStorage
from refineq.integrations.ocr import OpenAIVisionTransport, VisionTransport
from refineq.integrations.repository import IntegrationRepository


class IntegrationTester:
    def __init__(
        self,
        repository: IntegrationRepository,
        *,
        vision_transport: VisionTransport | None = None,
    ) -> None:
        self.repository = repository
        self.vision_transport = vision_transport or OpenAIVisionTransport()

    @staticmethod
    def _vision_test_image() -> bytes:
        document = fitz.open()
        try:
            page = document.new_page(width=180, height=72)
            page.insert_text((14, 42), "REFINEQ OCR TEST", fontsize=16)
            return page.get_pixmap(alpha=False).tobytes("png")
        finally:
            document.close()

    def test(self, kind: IntegrationKind, *, actor_id: str) -> IntegrationTestResult:
        integration = self.repository.load(kind)
        secrets = {name: value.get_secret_value() for name, value in integration.secrets.items()}
        try:
            if kind is IntegrationKind.CHAT:
                assert_safe_endpoint(
                    str(integration.config["base_url"]),
                    allow_private_network=bool(
                        integration.config.get("allow_private_network", False)
                    ),
                    allow_transparent_proxy=True,
                )
                client = OpenAI(
                    api_key=secrets["api_key"],
                    base_url=str(integration.config["base_url"]),
                    timeout=15.0,
                    http_client=DefaultHttpxClient(follow_redirects=False),
                )
                client.chat.completions.create(
                    model=str(integration.config["model"]),
                    messages=[{"role": "user", "content": "Reply OK"}],
                    max_tokens=2,
                )
            elif kind is IntegrationKind.EMBEDDING:
                assert_safe_endpoint(
                    str(integration.config["base_url"]),
                    allow_private_network=bool(
                        integration.config.get("allow_private_network", False)
                    ),
                    allow_transparent_proxy=True,
                )
                client = OpenAI(
                    api_key=secrets["api_key"],
                    base_url=str(integration.config["base_url"]),
                    timeout=15.0,
                    http_client=DefaultHttpxClient(follow_redirects=False),
                )
                client.embeddings.create(
                    model=str(integration.config["model"]),
                    input=["RefineQ connection test"],
                    dimensions=int(integration.config["dimensions"]),
                )
            elif kind is IntegrationKind.OCR:
                response = self.vision_transport.recognize(
                    settings=integration,
                    images=[self._vision_test_image()],
                )
                if not response.strip():
                    raise RuntimeError("OCR provider returned no text for the vision test")
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
