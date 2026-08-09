"""Typed learning-domain values with no storage or HTTP dependencies."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


class KnowledgeType(StrEnum):
    MEMORY = "memory"
    CONCEPT = "concept"
    PROCEDURE = "procedure"
    DESIGN = "design"


class LearningMode(StrEnum):
    """How a learner wants to build a capability in the current session."""

    CONCEPT = "concept"
    CASE = "case"
    PROJECT = "project"
    EXAM = "exam"


class Grounding(StrEnum):
    """Whether a learning task is supported by retrieved user material."""

    MATERIAL = "material"
    GENERAL = "general"


class BKTState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    p_mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    p_learn: float = Field(default=0.15, ge=0.0, le=1.0)
    p_guess: float = Field(default=0.2, ge=0.0, le=1.0)
    p_slip: float = Field(default=0.1, ge=0.0, le=1.0)
    evidence_count: int = Field(default=0, ge=0)
    credited_question_ids: list[str] = Field(default_factory=list, max_length=50)


class DifficultyState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    level: int = Field(default=2, ge=1, le=5)
    consecutive_wrong: int = Field(default=0, ge=0)
    recent_correct_question_ids: list[str] = Field(default_factory=list)
    recent_wrong_question_ids: list[str] = Field(default_factory=list)


class LearningEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    kind: Literal["attempt", "diagnostic", "review", "self_explanation", "material"]
    source_id: str = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=1000)
    observed_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)

    _normalize_observed_at = field_validator("observed_at", mode="after")(_as_utc)


class StudySession(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    topic_id: str = Field(min_length=1)
    planned_at: datetime
    minutes: int = Field(ge=5, le=480)
    activity: Literal["learn", "practice", "apply", "review"] = "practice"
    status: Literal["planned", "completed"] = "planned"

    _normalize_planned_at = field_validator("planned_at", mode="after")(_as_utc)


class StudyPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    goal: str = Field(min_length=1, max_length=500)
    exam_at: datetime
    daily_minutes: int = Field(ge=5, le=480)
    sessions: list[StudySession] = Field(min_length=1)

    _normalize_exam_at = field_validator("exam_at", mode="after")(_as_utc)
