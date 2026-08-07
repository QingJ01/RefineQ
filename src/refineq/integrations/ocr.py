"""OpenAI-compatible visual OCR fallback for scanned PDFs."""

from __future__ import annotations

import base64
from typing import Protocol

import fitz
from openai import OpenAI

from refineq.integrations.models import IntegrationKind, IntegrationSettings
from refineq.integrations.repository import (
    IntegrationNotConfiguredError,
    IntegrationRepository,
)


class OcrError(ValueError):
    """Raised when OCR cannot produce safe, usable text."""


class VisionTransport(Protocol):
    def recognize(self, *, settings: IntegrationSettings, images: list[bytes]) -> str: ...


class OpenAIVisionTransport:
    def recognize(self, *, settings: IntegrationSettings, images: list[bytes]) -> str:
        client = OpenAI(
            api_key=settings.secrets["api_key"].get_secret_value(),
            base_url=str(settings.config["base_url"]),
            timeout=60.0,
        )
        content: list[dict[str, object]] = [
            {
                "type": "text",
                "text": (
                    "Transcribe every page faithfully in page order. Preserve headings, lists, "
                    "tables, mathematical notation, and line breaks. Return only the transcription."
                ),
            }
        ]
        content.extend(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64.b64encode(image).decode('ascii')}"
                },
            }
            for image in images
        )
        response = client.chat.completions.create(
            model=str(settings.config["model"]),
            messages=[{"role": "user", "content": content}],
            max_tokens=8_000,
        )
        return response.choices[0].message.content or ""


class OcrService:
    def __init__(
        self,
        integrations: IntegrationRepository,
        *,
        transport: VisionTransport | None = None,
        max_pages: int = 50,
        max_chars: int = 2_000_000,
    ) -> None:
        self.integrations = integrations
        self.transport = transport or OpenAIVisionTransport()
        self.max_pages = max_pages
        self.max_chars = max_chars

    def _settings(self) -> IntegrationSettings:
        settings = self.integrations.load(IntegrationKind.OCR)
        if not settings.enabled or "api_key" not in settings.secrets:
            raise IntegrationNotConfiguredError("OCR integration is not enabled")
        return settings

    def available(self) -> bool:
        try:
            self._settings()
        except IntegrationNotConfiguredError:
            return False
        return True

    def extract(self, filename: str, content_type: str, payload: bytes) -> str:
        del content_type
        if not filename.lower().endswith(".pdf"):
            raise OcrError("OCR fallback currently supports PDF files")
        settings = self._settings()
        try:
            with fitz.open(stream=payload, filetype="pdf") as document:
                if document.page_count > self.max_pages:
                    raise OcrError("Scanned PDF exceeds the OCR page limit")
                images = [
                    page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).tobytes("png")
                    for page in document
                ]
        except OcrError:
            raise
        except (RuntimeError, ValueError) as error:
            raise OcrError("Scanned PDF could not be rendered for OCR") from error
        if not images:
            raise OcrError("Scanned PDF contains no pages")
        try:
            text = self.transport.recognize(settings=settings, images=images).strip()
        except Exception as error:
            raise OcrError("OCR provider failed to process the scanned PDF") from error
        if not text:
            raise OcrError("OCR provider returned no text")
        if len(text) > self.max_chars:
            raise OcrError("OCR text exceeds the extracted character limit")
        return text
