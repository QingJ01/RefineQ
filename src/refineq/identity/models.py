"""Public identity models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class User(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=100)
    role: Literal["learner", "admin"] = "learner"
    created_at: datetime

    @field_validator("created_at", mode="after")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: SecretStr
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("password", mode="after")
    @classmethod
    def validate_password_bytes(cls, value: SecretStr) -> SecretStr:
        size = len(value.get_secret_value().encode("utf-8"))
        if not 12 <= size <= 72:
            raise ValueError("password must contain 12 to 72 UTF-8 bytes")
        return value

    @field_validator("display_name", mode="after")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("display_name must not be blank")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)
    password: SecretStr

    @field_validator("password", mode="after")
    @classmethod
    def validate_password_bytes(cls, value: SecretStr) -> SecretStr:
        size = len(value.get_secret_value().encode("utf-8"))
        if not 1 <= size <= 72:
            raise ValueError("password must contain 1 to 72 UTF-8 bytes")
        return value


class PasswordResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)


class PasswordResetAccepted(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool = True
    reset_token: str | None = None


class AuthCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password_reset_available: bool


class PasswordResetComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=500)
    password: SecretStr

    @field_validator("password", mode="after")
    @classmethod
    def validate_password_bytes(cls, value: SecretStr) -> SecretStr:
        size = len(value.get_secret_value().encode("utf-8"))
        if not 12 <= size <= 72:
            raise ValueError("password must contain 12 to 72 UTF-8 bytes")
        return value


class AuthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"
    user: User


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name", mode="after")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("display_name must not be blank")
        return normalized


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: SecretStr
    new_password: SecretStr

    @field_validator("current_password", mode="after")
    @classmethod
    def validate_current_password(cls, value: SecretStr) -> SecretStr:
        size = len(value.get_secret_value().encode("utf-8"))
        if not 1 <= size <= 72:
            raise ValueError("current_password must contain 1 to 72 UTF-8 bytes")
        return value

    @field_validator("new_password", mode="after")
    @classmethod
    def validate_new_password(cls, value: SecretStr) -> SecretStr:
        size = len(value.get_secret_value().encode("utf-8"))
        if not 12 <= size <= 72:
            raise ValueError("new_password must contain 12 to 72 UTF-8 bytes")
        return value


class AccountDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_password: SecretStr
    confirmation: str = Field(min_length=3, max_length=254)


class AccountExportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exported_at: datetime
    user: User
    records: list[dict[str, Any]] = Field(default_factory=list)
    materials: list[dict[str, Any]] = Field(default_factory=list)
