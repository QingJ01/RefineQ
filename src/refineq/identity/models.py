"""Public identity models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

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


class AuthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    token_type: str = "bearer"
    user: User
