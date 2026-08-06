"""Upload allowlist and resource-limit policy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SUPPORTED_MIME_TYPES: dict[str, frozenset[str]] = {
    ".txt": frozenset({"text/plain", "application/octet-stream"}),
    ".md": frozenset({"text/markdown", "text/plain", "application/octet-stream"}),
    ".pdf": frozenset({"application/pdf"}),
    ".docx": frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
}


class MaterialPolicyError(ValueError):
    def __init__(self, message: str, *, code: str = "unsupported_material") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class UploadDescriptor:
    filename: str
    content_type: str
    size: int


class MaterialPolicy:
    def __init__(
        self,
        *,
        max_files: int = 10,
        max_file_bytes: int = 20 * 1024 * 1024,
        max_batch_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes
        self.max_batch_bytes = max_batch_bytes

    @staticmethod
    def _validate_descriptor(descriptor: UploadDescriptor) -> None:
        filename = descriptor.filename
        if (
            not filename
            or filename in {".", ".."}
            or "/" in filename
            or "\\" in filename
            or Path(filename).name != filename
        ):
            raise MaterialPolicyError("Upload filename must not contain a path")
        extension = Path(filename).suffix.lower()
        supported_mimes = SUPPORTED_MIME_TYPES.get(extension)
        if supported_mimes is None:
            raise MaterialPolicyError(f"Unsupported file extension: {extension or '(none)'}")
        content_type = descriptor.content_type.split(";", 1)[0].strip().lower()
        if content_type not in supported_mimes:
            raise MaterialPolicyError(f"MIME type {content_type!r} does not match {extension}")
        if descriptor.size < 0:
            raise MaterialPolicyError("Upload size must not be negative", code="material_limit")

    def validate_batch(self, uploads: list[UploadDescriptor]) -> None:
        if not uploads:
            raise MaterialPolicyError("At least one file is required")
        if len(uploads) > self.max_files:
            raise MaterialPolicyError("Too many files in one upload", code="material_limit")
        for upload in uploads:
            self._validate_descriptor(upload)
            if upload.size > self.max_file_bytes:
                raise MaterialPolicyError(
                    "File exceeds the per-file limit",
                    code="material_limit",
                )
        if sum(upload.size for upload in uploads) > self.max_batch_bytes:
            raise MaterialPolicyError(
                "Upload exceeds the batch limit",
                code="material_limit",
            )
