"""Typed runtime configuration owned by the RefineQ application."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
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

    @field_validator("data_root", mode="after")
    @classmethod
    def resolve_data_root(cls, value: Path) -> Path:
        """Make every storage operation use one unambiguous absolute root."""

        return value.expanduser().resolve()
