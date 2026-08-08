"""Typed material-analysis results used by later onboarding and planning steps."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MaterialType(StrEnum):
    TEXTBOOK = "textbook"
    LECTURE_NOTES = "lecture_notes"
    EXAM = "exam"
    PROBLEM_SET = "problem_set"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class MaterialSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1, max_length=300)
    topics: list[str] = Field(default_factory=list, max_length=20)
    citation_ids: list[str] = Field(default_factory=list, max_length=20)


class MaterialAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    material_id: str
    filename: str
    material_type: MaterialType
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=1_500)
    sections: list[MaterialSection] = Field(default_factory=list, max_length=80)
    topics: list[str] = Field(default_factory=list, max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)
    mode: str = Field(pattern=r"^(ai|fallback)$")
    analyzed_at: datetime

    @field_validator("analyzed_at", mode="after")
    @classmethod
    def normalize_analyzed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("analyzed_at must be timezone-aware")
        return value.astimezone(UTC)


class MaterialAnalysisModelOutput(BaseModel):
    """Strict model response before server-owned metadata is attached."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    material_type: MaterialType
    title: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=1_500)
    sections: list[MaterialSection] = Field(default_factory=list, max_length=80)
    topics: list[str] = Field(default_factory=list, max_length=200)
    confidence: float = Field(ge=0.0, le=1.0)
