"""Bounded local text extraction for the supported material formats."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import fitz
from docx import Document


class MaterialExtractionError(ValueError):
    """Raised when a supported file cannot yield usable text."""


def _extract_pdf(data: bytes) -> str:
    try:
        with fitz.open(stream=data, filetype="pdf") as document:
            return "\n".join(page.get_text("text") for page in document)
    except (RuntimeError, ValueError) as error:
        raise MaterialExtractionError("PDF could not be parsed") from error


def _extract_docx(data: bytes) -> str:
    try:
        document = Document(BytesIO(data))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    except (KeyError, OSError, ValueError) as error:
        raise MaterialExtractionError("DOCX could not be parsed") from error


def extract_text(filename: str, content_type: str, data: bytes) -> str:
    """Extract normalized text without executing or rendering uploaded content."""

    del content_type
    extension = Path(filename).suffix.lower()
    if extension in {".txt", ".md"}:
        try:
            extracted = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise MaterialExtractionError("Text material must use UTF-8") from error
    elif extension == ".pdf":
        extracted = _extract_pdf(data)
    elif extension == ".docx":
        extracted = _extract_docx(data)
    else:
        raise MaterialExtractionError(f"Unsupported material extension: {extension}")

    normalized = "\n".join(line.rstrip() for line in extracted.splitlines()).strip()
    if not normalized:
        raise MaterialExtractionError("Material contains no extractable text")
    return normalized
