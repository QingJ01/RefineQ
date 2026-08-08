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


class ErrorType(StrEnum):
    UNKNOWN = "unknown"
    STRUCTURAL = "structural"
    DEVIATION = "deviation"
    APPLICATION = "application"
    METACOGNITIVE = "metacognitive"


class ReviewRating(StrEnum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class LearningMode(StrEnum):
    """How a learner wants to build a capability in the current session."""

    CONCEPT = "concept"
    CASE = "case"
    PROJECT = "project"
    EXAM = "exam"


class BKTState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    p_mastery: float = Field(default=0.2, ge=0.0, le=1.0)
    p_learn: float = Field(default=0.15, ge=0.0, le=1.0)
    p_guess: float = Field(default=0.2, ge=0.0, le=1.0)
    p_slip: float = Field(default=0.1, ge=0.0, le=1.0)
    evidence_count: int = Field(default=0, ge=0)


class DiagnosticCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    knowledge_point_id: str = Field(min_length=1)
    p_mastery: float = Field(default=0.5, ge=0.0, le=1.0)
    assessment_count: int = Field(default=0, ge=0)
    recent_errors: int = Field(default=0, ge=0)
    exam_weight: float = Field(default=1.0, ge=0.0, le=5.0)
    prerequisite_gap: float = Field(default=0.0, ge=0.0, le=1.0)


class AdaptiveDiagnosticSession(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    answer_count: int = Field(default=0, ge=0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    minimum_questions: int = Field(default=8, ge=1)
    maximum_questions: int = Field(default=12, ge=1)


class DifficultyState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    level: int = Field(default=2, ge=1, le=5)
    consecutive_wrong: int = Field(default=0, ge=0)
    recent_correct_question_ids: list[str] = Field(default_factory=list)


class ErrorDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    category: ErrorType = ErrorType.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)
    explanation: str = "Insufficient evidence to determine the error category."
    is_confirmed: bool = False


class ReviewState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    knowledge_point_id: str = Field(min_length=1)
    due_at: datetime
    interval_days: int = Field(default=0, ge=0)
    streak: int = Field(default=0, ge=0)
    lapses: int = Field(default=0, ge=0)

    _normalize_due_at = field_validator("due_at", mode="after")(_as_utc)


class ReviewTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    knowledge_point_id: str = Field(min_length=1)
    knowledge_type: KnowledgeType
    state: ReviewState


class LearningEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    kind: Literal["attempt", "diagnostic", "review", "self_explanation", "material"]
    source_id: str = Field(min_length=1)
    summary: str = Field(min_length=1, max_length=1000)
    observed_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)

    _normalize_observed_at = field_validator("observed_at", mode="after")(_as_utc)


class LearningRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    action: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=1000)
    evidence_ids: list[str] = Field(min_length=1)


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
