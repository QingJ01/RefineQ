"""Typed read models for the cross-workspace calendar."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


class CalendarTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    workspace_title: str = Field(min_length=1, max_length=200)
    workspace_archived: bool = False
    topic_id: str = Field(min_length=1)
    topic_label: str = Field(min_length=1, max_length=200)
    planned_at: datetime
    minutes: int = Field(ge=5, le=480)
    activity: Literal["learn", "practice", "apply", "review"]
    status: Literal["planned", "completed"]

    _normalize_planned_at = field_validator("planned_at", mode="after")(_as_utc)


class CalendarResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    starts_at: datetime
    ends_at: datetime
    tasks: list[CalendarTask]

    _normalize_starts_at = field_validator("starts_at", mode="after")(_as_utc)
    _normalize_ends_at = field_validator("ends_at", mode="after")(_as_utc)
