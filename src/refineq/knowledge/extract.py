"""Bounded local text extraction for the supported material formats."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from time import monotonic
from zipfile import BadZipFile, LargeZipFile, ZipFile

import fitz
from docx import Document


class MaterialExtractionError(ValueError):
    """Raised when a supported file cannot yield usable text."""


class MaterialExtractionLimitError(MaterialExtractionError):
    """Raised when extraction exceeds a configured resource budget."""


@dataclass(frozen=True, slots=True)
class ExtractionLimits:
    max_pdf_pages: int = 500
    max_docx_entries: int = 2_000
    max_docx_expanded_bytes: int = 100 * 1024 * 1024
    max_docx_compression_ratio: float = 100.0
    max_extracted_chars: int = 2_000_000
    max_processing_seconds: float = 15.0

    def __post_init__(self) -> None:
        if (
            min(
                self.max_pdf_pages,
                self.max_docx_entries,
                self.max_docx_expanded_bytes,
                self.max_extracted_chars,
            )
            < 1
        ):
            raise ValueError("extraction limits must be positive")
        if self.max_docx_compression_ratio <= 0 or self.max_processing_seconds <= 0:
            raise ValueError("extraction ratio and time limits must be positive")


def _check_deadline(started_at: float, limits: ExtractionLimits) -> None:
    if monotonic() - started_at > limits.max_processing_seconds:
        raise MaterialExtractionLimitError("Material extraction exceeded its time budget")


def _extract_pdf(data: bytes, limits: ExtractionLimits, started_at: float) -> str:
    try:
        with fitz.open(stream=data, filetype="pdf") as document:
            if document.page_count > limits.max_pdf_pages:
                raise MaterialExtractionLimitError("PDF exceeds the page limit")
            pages: list[str] = []
            extracted_chars = 0
            for page in document:
                _check_deadline(started_at, limits)
                page_text = page.get_text("text")
                extracted_chars += len(page_text)
                if extracted_chars > limits.max_extracted_chars:
                    raise MaterialExtractionLimitError(
                        "Material exceeds the extracted character limit"
                    )
                pages.append(page_text)
            return "\n".join(pages)
    except MaterialExtractionLimitError:
        raise
    except (RuntimeError, ValueError) as error:
        raise MaterialExtractionError("PDF could not be parsed") from error


def _preflight_docx(data: bytes, limits: ExtractionLimits) -> None:
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > limits.max_docx_entries:
                raise MaterialExtractionLimitError("DOCX has too many archive entries")
            if any(entry.flag_bits & 0x1 for entry in entries):
                raise MaterialExtractionError("Encrypted DOCX files are not supported")
            expanded_bytes = sum(entry.file_size for entry in entries)
            if expanded_bytes > limits.max_docx_expanded_bytes:
                raise MaterialExtractionLimitError("DOCX exceeds the expanded byte limit")
            compression_ratio = expanded_bytes / max(1, len(data))
            if compression_ratio > limits.max_docx_compression_ratio:
                raise MaterialExtractionLimitError("DOCX exceeds the compression ratio limit")
    except MaterialExtractionError:
        raise
    except (BadZipFile, LargeZipFile, OSError, ValueError) as error:
        raise MaterialExtractionError("DOCX could not be parsed") from error


def _extract_docx(data: bytes, limits: ExtractionLimits, started_at: float) -> str:
    _preflight_docx(data, limits)
    _check_deadline(started_at, limits)
    try:
        document = Document(BytesIO(data))
        paragraphs: list[str] = []
        extracted_chars = 0
        for paragraph in document.paragraphs:
            _check_deadline(started_at, limits)
            extracted_chars += len(paragraph.text)
            if extracted_chars > limits.max_extracted_chars:
                raise MaterialExtractionLimitError("Material exceeds the extracted character limit")
            paragraphs.append(paragraph.text)
        return "\n".join(paragraphs)
    except MaterialExtractionLimitError:
        raise
    except (KeyError, OSError, ValueError) as error:
        raise MaterialExtractionError("DOCX could not be parsed") from error


def extract_text(
    filename: str,
    content_type: str,
    data: bytes,
    *,
    limits: ExtractionLimits | None = None,
) -> str:
    """Extract normalized text without executing or rendering uploaded content."""

    del content_type
    limits = limits or ExtractionLimits()
    started_at = monotonic()
    extension = Path(filename).suffix.lower()
    if extension in {".txt", ".md"}:
        try:
            extracted = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise MaterialExtractionError("Text material must use UTF-8") from error
    elif extension == ".pdf":
        extracted = _extract_pdf(data, limits, started_at)
    elif extension == ".docx":
        extracted = _extract_docx(data, limits, started_at)
    else:
        raise MaterialExtractionError(f"Unsupported material extension: {extension}")

    _check_deadline(started_at, limits)
    if len(extracted) > limits.max_extracted_chars:
        raise MaterialExtractionLimitError("Material exceeds the extracted character limit")
    normalized = "\n".join(line.rstrip() for line in extracted.splitlines()).strip()
    if not normalized:
        raise MaterialExtractionError("Material contains no extractable text")
    return normalized
