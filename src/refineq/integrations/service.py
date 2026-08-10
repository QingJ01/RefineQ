"""Safe live checks for administrator-managed integrations."""

from __future__ import annotations

import math
from typing import Literal

import fitz
from openai import DefaultHttpxClient, OpenAI
from pydantic import BaseModel, ConfigDict, Field

from refineq.agent.settings import ModelSettings
from refineq.agent.structured import (
    OpenAICompatibleStructuredTransport,
    StructuredModelTransport,
)
from refineq.integrations.endpoints import assert_safe_endpoint
from refineq.integrations.models import IntegrationKind, IntegrationTestResult
from refineq.integrations.object_storage import S3ObjectStorage
from refineq.integrations.ocr import OpenAIVisionTransport, VisionTransport
from refineq.integrations.repository import IntegrationRepository


class _ChatClassificationProbe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["direct_answer"]
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class _ChatAnswerProbe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str = Field(min_length=1)
    basis: str = Field(min_length=1)
    convertible_goal: bool


class _ChatCapabilityProbe(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"]
    classification: _ChatClassificationProbe
    answer: _ChatAnswerProbe


class IntegrationTester:
    def __init__(
        self,
        repository: IntegrationRepository,
        *,
        vision_transport: VisionTransport | None = None,
        chat_transport: StructuredModelTransport | None = None,
    ) -> None:
        self.repository = repository
        self.vision_transport = vision_transport or OpenAIVisionTransport()
        self.chat_transport = chat_transport or OpenAICompatibleStructuredTransport(
            timeout=15.0,
            max_retries=0,
        )

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
                self.chat_transport.complete(
                    settings=ModelSettings(
                        api_key=secrets["api_key"],
                        base_url=str(integration.config["base_url"]),
                        model=str(integration.config["model"]),
                        temperature=float(integration.config.get("temperature", 0.2)),
                        allow_private_network=bool(
                            integration.config.get("allow_private_network", False)
                        ),
                    ),
                    response_model=_ChatCapabilityProbe,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Return a JSON capability probe. Use status ok; classify this as "
                                "direct_answer with a short reason and confidence; provide a "
                                "bounded answer with basis and convertible_goal false."
                            ),
                        },
                        {
                            "role": "user",
                            "content": "What is spaced repetition?",
                        },
                    ],
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
                response = client.embeddings.create(
                    model=str(integration.config["model"]),
                    input=["RefineQ connection test"],
                )
                expected_dimensions = int(integration.config["dimensions"])
                vector = list(response.data[0].embedding)
                if len(vector) != expected_dimensions or not all(
                    math.isfinite(value) for value in vector
                ):
                    raise RuntimeError(
                        "Embedding provider returned an invalid vector; "
                        f"expected {expected_dimensions} dimensions"
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

        message = (
            "Structured chat capability succeeded"
            if kind is IntegrationKind.CHAT
            else "Connection succeeded"
        )
        self.repository.record_test(kind, status="ok", message=message, actor_id=actor_id)
        return IntegrationTestResult(kind=kind, status="ok", message=message)

    @staticmethod
    def _sanitize(message: str, secrets: dict[str, str]) -> str:
        sanitized = message
        for secret in secrets.values():
            if secret:
                sanitized = sanitized.replace(secret, "[redacted]")
        return sanitized[:500] or "Connection failed"
