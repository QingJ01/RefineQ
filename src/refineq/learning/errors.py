"""Validation boundary for model-assisted answer error analysis."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from refineq.learning.models import ErrorDiagnosis, ErrorType


class _ErrorAnalysisPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: ErrorType
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(min_length=1, max_length=8)
    explanation: str = Field(min_length=1, max_length=1000)


def _unknown(
    *,
    confidence: float = 0.0,
    evidence: list[str] | None = None,
) -> ErrorDiagnosis:
    return ErrorDiagnosis(confidence=confidence, evidence=evidence or [])


def parse_error_analysis(
    value: Any,
    *,
    confidence_threshold: float = 0.65,
) -> ErrorDiagnosis:
    """Validate untrusted output and avoid turning weak guesses into facts."""

    try:
        payload = _ErrorAnalysisPayload.model_validate(value)
    except (ValidationError, TypeError, ValueError):
        return _unknown()

    evidence = [item.strip() for item in payload.evidence if item.strip()]
    if payload.category is ErrorType.UNKNOWN or payload.confidence < confidence_threshold:
        return _unknown(confidence=payload.confidence, evidence=evidence)
    return ErrorDiagnosis(
        category=payload.category,
        confidence=payload.confidence,
        evidence=evidence,
        explanation=payload.explanation.strip(),
        is_confirmed=True,
    )
