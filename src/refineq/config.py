"""Typed runtime configuration owned by the RefineQ application."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator, model_validator
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
    backup_root: Path | None = None
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
    public_site_url: str = "http://localhost"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_from_email: str | None = None
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = True
    smtp_use_ssl: bool = False
    smtp_timeout_seconds: float = Field(default=10.0, gt=0.0, le=120.0)
    demo_email: str = "learner@refineq.local"
    demo_password: SecretStr | None = None
    auth_rate_limit_requests: int = Field(default=30, ge=1, le=100_000)
    mutation_rate_limit_requests: int = Field(default=240, ge=1, le=1_000_000)
    rate_limit_window_seconds: float = Field(default=60.0, gt=0.0, le=3_600.0)
    mcp_enabled: bool = False
    mcp_internal_secret: SecretStr | None = None
    mcp_account_email: str | None = None
    mcp_allowed_hosts: str = ""
    mcp_run_ttl_seconds: int = Field(default=300, ge=60, le=3_600)
    mcp_idempotency_ttl_seconds: int = Field(default=86_400, ge=300, le=604_800)
    mcp_read_rate_limit: int = Field(default=120, ge=1, le=100_000)
    mcp_write_rate_limit: int = Field(default=30, ge=1, le=100_000)

    @field_validator("data_root", mode="after")
    @classmethod
    def resolve_data_root(cls, value: Path) -> Path:
        """Make every storage operation use one unambiguous absolute root."""

        return value.expanduser().resolve()

    @field_validator("backup_root", mode="after")
    @classmethod
    def resolve_backup_root(cls, value: Path | None) -> Path | None:
        """Normalize an explicit durable-backup location."""

        return None if value is None else value.expanduser().resolve()

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

    @field_validator("mcp_account_email", mode="after")
    @classmethod
    def normalize_mcp_account_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
            raise ValueError("MCP account email must be a valid address")
        return normalized

    @model_validator(mode="after")
    def validate_password_reset_delivery(self) -> Settings:
        """Reject partial SMTP configuration before the API starts."""

        public_site_url = self.public_site_url.strip()
        parsed_site_url = urlsplit(public_site_url)
        if (
            parsed_site_url.scheme.lower() not in {"http", "https"}
            or parsed_site_url.hostname is None
            or parsed_site_url.query
            or parsed_site_url.fragment
        ):
            raise ValueError(
                "public site URL must be an HTTP(S) URL with a host and no query or fragment"
            )

        host = (self.smtp_host or "").strip()
        sender = (self.smtp_from_email or "").strip()
        username = (self.smtp_username or "").strip()
        has_password = bool(
            self.smtp_password is not None and self.smtp_password.get_secret_value().strip()
        )
        if bool(host) != bool(sender):
            raise ValueError("SMTP host and sender must be configured together")
        if not host and (username or has_password):
            raise ValueError("SMTP credentials require an SMTP host and sender")
        if bool(username) != has_password:
            raise ValueError("SMTP username and password must be configured together")
        if self.smtp_starttls and self.smtp_use_ssl:
            raise ValueError("SMTP STARTTLS and implicit TLS cannot both be enabled")
        if self.resolved_backup_root.is_relative_to(self.data_root):
            raise ValueError("backup root must be outside the data root")
        if self.mcp_enabled:
            secret = (
                self.mcp_internal_secret.get_secret_value().strip()
                if self.mcp_internal_secret is not None
                else ""
            )
            normalized_secret = secret.casefold()
            if (
                len(secret) < 32
                or len(set(secret)) < 8
                or any(
                    marker in normalized_secret
                    for marker in (
                        "change-me",
                        "replace-me",
                        "example",
                        "your-secret",
                        "secret-here",
                    )
                )
            ):
                raise ValueError("enabled MCP requires a strong internal signing secret")
            if not self.mcp_account_email:
                raise ValueError("enabled MCP requires a bound account email")
            if not self.allowed_mcp_hosts:
                raise ValueError("enabled MCP requires at least one allowed host")
            if any(
                not host or "://" in host or any(character in host for character in "/*?# ")
                for host in self.allowed_mcp_hosts
            ):
                raise ValueError("MCP allowed hosts must be exact Host header values")
        self.public_site_url = public_site_url
        return self

    @property
    def resolved_database_url(self) -> str:
        """Return the configured production URL or an isolated development database."""

        if self.database_url is not None and self.database_url.get_secret_value().strip():
            return self.database_url.get_secret_value().strip()
        database_path = self.data_root / "system" / "refineq.sqlite3"
        return f"sqlite+pysqlite:///{database_path.as_posix()}"

    @property
    def resolved_backup_root(self) -> Path:
        """Return a backup location that cannot be captured inside its own archive."""

        if self.backup_root is not None:
            return self.backup_root
        return (self.data_root.parent / f"{self.data_root.name}-backups").resolve()

    @property
    def smtp_enabled(self) -> bool:
        return bool((self.smtp_host or "").strip() and (self.smtp_from_email or "").strip())

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

    @property
    def allowed_mcp_hosts(self) -> set[str]:
        """Return normalized hosts accepted by the MCP transport."""

        return {
            host.strip().lower().rstrip(".")
            for host in self.mcp_allowed_hosts.split(",")
            if host.strip()
        }
