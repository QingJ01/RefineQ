"""Optional OCR fallback tests for scanned study material."""

from __future__ import annotations

import fitz
import pytest

from refineq.database.engine import Database
from refineq.identity.service import IdentityService
from refineq.integrations.models import IntegrationKind, IntegrationUpdate
from refineq.integrations.ocr import OcrError, OcrService
from refineq.integrations.repository import IntegrationRepository
from refineq.integrations.service import IntegrationTester
from refineq.operations.admin import ensure_admin


class FakeVisionTransport:
    def __init__(self) -> None:
        self.image_count = 0
        self.batch_sizes: list[int] = []

    def recognize(self, *, settings, images: list[bytes]) -> str:
        del settings
        self.image_count += len(images)
        self.batch_sizes.append(len(images))
        return f"OCR extracted calculus notes batch {len(self.batch_sizes)}"


def _configured_repository(tmp_path) -> IntegrationRepository:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'ocr.sqlite3').as_posix()}")
    database.initialize()
    admin = ensure_admin(
        IdentityService(database),
        email="admin@example.com",
        password="correct-horse-battery-staple",
        display_name="Admin",
    ).user
    repository = IntegrationRepository(database, key_path=tmp_path / "key")
    repository.save(
        IntegrationKind.OCR,
        IntegrationUpdate(
            enabled=True,
            config={
                "base_url": "https://api.openai.com/v1",
                "model": "gpt-4.1-mini",
            },
            secrets={"api_key": "ocr-secret"},
        ),
        actor_id=admin.id,
    )
    return repository


def test_scanned_pdf_pages_are_rendered_and_sent_to_vision_provider(tmp_path) -> None:
    document = fitz.open()
    document.new_page(width=200, height=200)
    payload = document.tobytes()
    document.close()
    transport = FakeVisionTransport()
    service = OcrService(_configured_repository(tmp_path), transport=transport, max_pages=5)

    text = service.extract("scan.pdf", "application/pdf", payload)

    assert text == "OCR extracted calculus notes batch 1"
    assert transport.image_count == 1


def test_ocr_is_unavailable_when_the_admin_has_not_enabled_it(tmp_path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'empty.sqlite3').as_posix()}")
    database.initialize()
    repository = IntegrationRepository(database, key_path=tmp_path / "key")

    assert OcrService(repository).available() is False


def test_mixed_pdf_ocr_preserves_text_pages_and_only_renders_scanned_pages(tmp_path) -> None:
    document = fitz.open()
    text_page = document.new_page(width=200, height=200)
    text_page.insert_text((20, 40), "Local calculus explanation")
    document.new_page(width=200, height=200)
    payload = document.tobytes()
    document.close()
    transport = FakeVisionTransport()
    service = OcrService(_configured_repository(tmp_path), transport=transport, max_pages=5)

    text = service.extract(
        "mixed.pdf",
        "application/pdf",
        payload,
        local_text="Local calculus explanation",
    )

    assert "Local calculus explanation" in text
    assert "OCR extracted calculus notes batch 1" in text
    assert transport.image_count == 1


def test_scanned_pages_are_sent_in_small_consecutive_batches(tmp_path) -> None:
    document = fitz.open()
    for _ in range(5):
        document.new_page(width=100, height=100)
    payload = document.tobytes()
    document.close()
    transport = FakeVisionTransport()
    service = OcrService(
        _configured_repository(tmp_path),
        transport=transport,
        max_pages=5,
        max_images_per_request=2,
    )

    service.extract("scan.pdf", "application/pdf", payload)

    assert transport.batch_sizes == [2, 2, 1]


def test_ocr_rejects_page_before_rendering_when_pixel_budget_is_exceeded(tmp_path) -> None:
    document = fitz.open()
    document.new_page(width=500, height=500)
    payload = document.tobytes()
    document.close()
    service = OcrService(
        _configured_repository(tmp_path),
        transport=FakeVisionTransport(),
        max_page_pixels=1_000,
    )

    with pytest.raises(OcrError, match="pixel"):
        service.extract("scan.pdf", "application/pdf", payload)


def test_ocr_rejects_rendered_images_over_the_encoded_byte_budget(tmp_path) -> None:
    document = fitz.open()
    document.new_page(width=200, height=200)
    payload = document.tobytes()
    document.close()
    service = OcrService(
        _configured_repository(tmp_path),
        transport=FakeVisionTransport(),
        max_image_bytes=1,
    )

    with pytest.raises(OcrError, match="image byte"):
        service.extract("scan.pdf", "application/pdf", payload)


def test_ocr_connection_test_sends_a_real_image_to_the_vision_transport(tmp_path) -> None:
    repository = _configured_repository(tmp_path)
    transport = FakeVisionTransport()
    actor_id = repository.list_audit_logs()[0]["actor_id"]

    result = IntegrationTester(repository, vision_transport=transport).test(
        IntegrationKind.OCR,
        actor_id=str(actor_id),
    )

    assert result.status == "ok"
    assert transport.image_count == 1


def test_ocr_connection_test_image_contains_visible_test_content() -> None:
    pixmap = fitz.Pixmap(IntegrationTester._vision_test_image())

    assert min(pixmap.samples) < 100
