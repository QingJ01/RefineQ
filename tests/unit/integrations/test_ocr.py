"""Optional OCR fallback tests for scanned study material."""

from __future__ import annotations

import fitz

from refineq.database.engine import Database
from refineq.identity.service import IdentityService
from refineq.integrations.models import IntegrationKind, IntegrationUpdate
from refineq.integrations.ocr import OcrService
from refineq.integrations.repository import IntegrationRepository
from refineq.operations.admin import ensure_admin


class FakeVisionTransport:
    def __init__(self) -> None:
        self.image_count = 0

    def recognize(self, *, settings, images: list[bytes]) -> str:
        del settings
        self.image_count = len(images)
        return "OCR extracted calculus notes"


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

    assert text == "OCR extracted calculus notes"
    assert transport.image_count == 1


def test_ocr_is_unavailable_when_the_admin_has_not_enabled_it(tmp_path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'empty.sqlite3').as_posix()}")
    database.initialize()
    repository = IntegrationRepository(database, key_path=tmp_path / "key")

    assert OcrService(repository).available() is False
