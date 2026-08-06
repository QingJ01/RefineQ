"""Typed runtime configuration owned by the RefineQ application."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded exclusively from ``REFINEQ_*`` variables."""

    model_config = SettingsConfigDict(
        env_prefix="REFINEQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_root: Path = Field(default_factory=lambda: Path("data").resolve())
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    model_endpoint_allowed_hosts: str = "api.openai.com"
    model_encryption_key: SecretStr | None = None
    material_max_count_per_user: int = Field(default=500, ge=1, le=100_000)
    material_max_bytes_per_user: int = Field(
        default=2 * 1024 * 1024 * 1024,
        ge=1,
    )
    material_max_pdf_pages: int = Field(default=500, ge=1, le=10_000)
    material_max_docx_entries: int = Field(default=2_000, ge=1, le=100_000)
    material_max_docx_expanded_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1,
    )
    material_max_docx_compression_ratio: float = Field(default=100.0, gt=1.0)
    material_max_extracted_chars: int = Field(default=2_000_000, ge=1)
    material_extraction_timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)
    max_workspaces_per_user: int = Field(default=100, ge=1, le=10_000)
    max_projects_per_user: int = Field(default=100, ge=1, le=10_000)
    max_agent_sessions_per_user: int = Field(default=200, ge=1, le=100_000)
    auth_rate_limit_requests: int = Field(default=30, ge=1, le=100_000)
    mutation_rate_limit_requests: int = Field(default=240, ge=1, le=1_000_000)
    rate_limit_window_seconds: float = Field(default=60.0, gt=0.0, le=3_600.0)

    @field_validator("data_root", mode="after")
    @classmethod
    def resolve_data_root(cls, value: Path) -> Path:
        """Make every storage operation use one unambiguous absolute root."""

        return value.expanduser().resolve()

    @property
    def allowed_model_hosts(self) -> set[str]:
        """Return normalized hostnames controlled by the server operator."""

        return {
            host.strip().lower().rstrip(".")
            for host in self.model_endpoint_allowed_hosts.split(",")
            if host.strip()
        }
