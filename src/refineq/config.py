"""Typed runtime configuration owned by the RefineQ application."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
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
    database_url: SecretStr | None = None
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    forwarded_allow_ips: str = "127.0.0.1"
    model_endpoint_allowed_hosts: str = "api.openai.com,api.deepseek.com,api.siliconflow.cn"
    object_storage_endpoint_allowed_hosts: str = ""
    model_encryption_key: SecretStr | None = None
    material_max_count_per_user: int = Field(default=500, ge=1, le=100_000)
    material_max_bytes_per_user: int = Field(
        default=2 * 1024 * 1024 * 1024,
        ge=1,
    )
    material_max_request_bytes: int = Field(default=52 * 1024 * 1024, ge=1)
    material_upload_max_concurrent_global: int = Field(default=2, ge=1, le=1_000)
    material_upload_max_concurrent_per_user: int = Field(default=1, ge=1, le=1_000)
    material_upload_body_idle_timeout_seconds: float = Field(default=10.0, gt=0.0, le=120.0)
    material_upload_body_total_timeout_seconds: float = Field(default=60.0, gt=0.0, le=600.0)
    material_max_pdf_pages: int = Field(default=500, ge=1, le=10_000)
    material_max_docx_entries: int = Field(default=2_000, ge=1, le=100_000)
    material_max_docx_expanded_bytes: int = Field(
        default=100 * 1024 * 1024,
        ge=1,
    )
    material_max_docx_compression_ratio: float = Field(default=100.0, gt=1.0)
    material_max_extracted_chars: int = Field(default=2_000_000, ge=1)
    material_extraction_timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)
    material_ocr_max_pages: int = Field(default=50, ge=1, le=500)
    material_ocr_max_images_per_request: int = Field(default=4, ge=1, le=20)
    material_ocr_max_page_pixels: int = Field(default=12_000_000, ge=1)
    material_ocr_max_total_pixels: int = Field(default=80_000_000, ge=1)
    material_ocr_max_image_bytes: int = Field(default=40 * 1024 * 1024, ge=1)
    max_workspaces_per_user: int = Field(default=100, ge=1, le=10_000)
    max_projects_per_user: int = Field(default=100, ge=1, le=10_000)
    max_agent_sessions_per_user: int = Field(default=200, ge=1, le=100_000)
    password_reset_expose_token: bool = False
    password_reset_ttl_minutes: int = Field(default=20, ge=5, le=120)
    demo_email: str = "learner@refineq.local"
    demo_password: SecretStr | None = None
    auth_rate_limit_requests: int = Field(default=30, ge=1, le=100_000)
    mutation_rate_limit_requests: int = Field(default=240, ge=1, le=1_000_000)
    rate_limit_window_seconds: float = Field(default=60.0, gt=0.0, le=3_600.0)

    @field_validator("data_root", mode="after")
    @classmethod
    def resolve_data_root(cls, value: Path) -> Path:
        """Make every storage operation use one unambiguous absolute root."""

        return value.expanduser().resolve()

    @field_validator("model_encryption_key", mode="after")
    @classmethod
    def validate_model_encryption_key(cls, value: SecretStr | None) -> SecretStr | None:
        """Reject invalid configured keys during startup instead of during a learner request."""

        if value is None or not value.get_secret_value():
            return value
        try:
            Fernet(value.get_secret_value().encode("ascii"))
        except (UnicodeEncodeError, ValueError) as exc:
            raise ValueError("model encryption key must be a valid Fernet key") from exc
        return value

    @field_validator("database_url", mode="after")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        """Limit persistence drivers to the two explicitly supported SQL dialects."""

        if value is None or not value.get_secret_value().strip():
            return None
        scheme = urlsplit(value.get_secret_value()).scheme.lower()
        if scheme not in {"postgresql+psycopg", "sqlite+pysqlite"}:
            raise ValueError("database URL must use PostgreSQL or SQLite")
        return value

    @property
    def resolved_database_url(self) -> str:
        """Return the configured production URL or an isolated development database."""

        if self.database_url is not None and self.database_url.get_secret_value().strip():
            return self.database_url.get_secret_value().strip()
        database_path = self.data_root / "system" / "refineq.sqlite3"
        return f"sqlite+pysqlite:///{database_path.as_posix()}"

    @property
    def allowed_model_hosts(self) -> set[str]:
        """Return normalized hostnames controlled by the server operator."""

        return {
            host.strip().lower().rstrip(".")
            for host in self.model_endpoint_allowed_hosts.split(",")
            if host.strip()
        }

    @property
    def allowed_object_storage_hosts(self) -> set[str]:
        """Return S3 endpoint hostnames controlled by the server operator."""

        return {
            host.strip().lower().rstrip(".")
            for host in self.object_storage_endpoint_allowed_hosts.split(",")
            if host.strip()
        }
