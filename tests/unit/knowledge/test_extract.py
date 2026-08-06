"""Tests for local study-material text extraction."""

from __future__ import annotations

from io import BytesIO

import fitz
from docx import Document

from refineq.knowledge.extract import extract_text


def test_extracts_utf8_text_and_markdown() -> None:
    assert (
        extract_text("notes.txt", "text/plain", "导数 derivative".encode())
        == "导数 derivative"
    )
    assert extract_text("notes.md", "text/markdown", b"# Limits\nContinuity") == (
        "# Limits\nContinuity"
    )


def test_extracts_pdf_text() -> None:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "The derivative measures local change.")
    payload = document.tobytes()
    document.close()

    extracted = extract_text("calculus.pdf", "application/pdf", payload)

    assert "derivative measures local change" in extracted


def test_extracts_docx_paragraphs() -> None:
    document = Document()
    document.add_heading("Calculus", level=1)
    document.add_paragraph("The chain rule composes derivatives.")
    buffer = BytesIO()
    document.save(buffer)

    extracted = extract_text(
        "calculus.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        buffer.getvalue(),
    )

    assert extracted == "Calculus\nThe chain rule composes derivatives."
