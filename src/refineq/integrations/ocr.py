"""OpenAI-compatible visual OCR fallback for scanned PDFs."""

from __future__ import annotations

import base64
from math import ceil
from typing import Protocol

import fitz
from openai import DefaultHttpxClient, OpenAI

from refineq.integrations.endpoints import assert_safe_endpoint
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
        assert_safe_endpoint(
            str(settings.config["base_url"]),
            allow_private_network=bool(settings.config.get("allow_private_network", False)),
            allow_transparent_proxy=True,
        )
        client = OpenAI(
            api_key=settings.secrets["api_key"].get_secret_value(),
            base_url=str(settings.config["base_url"]),
            timeout=60.0,
            http_client=DefaultHttpxClient(follow_redirects=False),
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
        max_images_per_request: int = 4,
        max_page_pixels: int = 12_000_000,
        max_total_pixels: int = 80_000_000,
        max_image_bytes: int = 40 * 1024 * 1024,
        render_scale: float = 1.5,
        min_text_chars_per_page: int = 8,
    ) -> None:
        if (
            min(
                max_pages,
                max_chars,
                max_images_per_request,
                max_page_pixels,
                max_total_pixels,
                max_image_bytes,
                min_text_chars_per_page,
            )
            < 1
            or render_scale <= 0
        ):
            raise ValueError("OCR limits must be positive")
        self.integrations = integrations
        self.transport = transport or OpenAIVisionTransport()
        self.max_pages = max_pages
        self.max_chars = max_chars
        self.max_images_per_request = max_images_per_request
        self.max_page_pixels = max_page_pixels
        self.max_total_pixels = max_total_pixels
        self.max_image_bytes = max_image_bytes
        self.render_scale = render_scale
        self.min_text_chars_per_page = min_text_chars_per_page

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

    def _recognize(self, settings: IntegrationSettings, images: list[bytes]) -> str:
        try:
            text = self.transport.recognize(settings=settings, images=images).strip()
        except Exception as error:
            raise OcrError("OCR provider failed to process the scanned PDF") from error
        if not text:
            raise OcrError("OCR provider returned no text")
        return text

    def extract(
        self,
        filename: str,
        content_type: str,
        payload: bytes,
        *,
        local_text: str | None = None,
    ) -> str:
        del content_type
        if not filename.lower().endswith(".pdf"):
            raise OcrError("OCR fallback currently supports PDF files")
        settings = self._settings()
        try:
            with fitz.open(stream=payload, filetype="pdf") as document:
                if document.page_count > self.max_pages:
                    raise OcrError("Scanned PDF exceeds the OCR page limit")
                if document.page_count == 0:
                    raise OcrError("Scanned PDF contains no pages")
                parts: list[str | None] = [None] * document.page_count
                pending_images: list[bytes] = []
                pending_indices: list[int] = []
                rendered_pixels = 0
                rendered_bytes = 0
                scanned_pages = 0

                def flush_pending() -> None:
                    if not pending_images:
                        return
                    parts[pending_indices[0]] = self._recognize(settings, pending_images)
                    pending_images.clear()
                    pending_indices.clear()

                for page_index, page in enumerate(document):
                    page_text = page.get_text("text").strip()
                    if len(page_text) >= self.min_text_chars_per_page:
                        flush_pending()
                        parts[page_index] = page_text
                        continue
                    scanned_pages += 1
                    width = ceil(float(page.rect.width) * self.render_scale)
                    height = ceil(float(page.rect.height) * self.render_scale)
                    page_pixels = width * height
                    if page_pixels > self.max_page_pixels:
                        raise OcrError("Scanned PDF page exceeds the OCR pixel limit")
                    rendered_pixels += page_pixels
                    if rendered_pixels > self.max_total_pixels:
                        raise OcrError("Scanned PDF exceeds the total OCR pixel limit")
                    image = page.get_pixmap(
                        matrix=fitz.Matrix(self.render_scale, self.render_scale),
                        alpha=False,
                    ).tobytes("png")
                    rendered_bytes += len(image)
                    if rendered_bytes > self.max_image_bytes:
                        raise OcrError("Scanned PDF exceeds the OCR image byte limit")
                    pending_images.append(image)
                    pending_indices.append(page_index)
                    if len(pending_images) >= self.max_images_per_request:
                        flush_pending()
                flush_pending()
        except OcrError:
            raise
        except (RuntimeError, ValueError) as error:
            raise OcrError("Scanned PDF could not be rendered for OCR") from error
        if scanned_pages == 0 and local_text is not None:
            text = local_text.strip()
        else:
            text = "\n\n".join(part for part in parts if part).strip()
        if not text:
            raise OcrError("OCR produced no usable text")
        if len(text) > self.max_chars:
            raise OcrError("OCR text exceeds the extracted character limit")
        return text
