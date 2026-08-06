"""Typed values for invisible personal learning workspaces."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


class LearningWorkspace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    title: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=100)
    goal: str = Field(min_length=1, max_length=500)
    topics: list[str] = Field(min_length=1, max_length=200)
    keywords: list[str] = Field(min_length=1, max_length=200)
    routing_summary: str = Field(min_length=1, max_length=500)
    created_at: datetime
    last_active_at: datetime

    _normalize_created_at = field_validator("created_at", mode="after")(_utc)
    _normalize_last_active_at = field_validator("last_active_at", mode="after")(_utc)


class WorkspaceRoutingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["created", "switched", "reused"]
    workspace_id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    subject: str = Field(min_length=1, max_length=100)
    topics: list[str] = Field(min_length=1, max_length=20)
    keywords: list[str] = Field(min_length=1, max_length=50)
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(min_length=1, max_length=500)

