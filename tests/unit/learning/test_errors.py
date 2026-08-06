"""Tests for the model-output error-analysis boundary."""

from __future__ import annotations

from refineq.learning.errors import parse_error_analysis
from refineq.learning.models import ErrorType


def test_valid_error_analysis_preserves_evidence() -> None:
    diagnosis = parse_error_analysis(
        {
            "category": "application",
            "confidence": 0.91,
            "evidence": ["Used the product rule where the chain rule was required."],
            "explanation": "The concept was recalled but used in the wrong setting.",
        }
    )

    assert diagnosis.category is ErrorType.APPLICATION
    assert diagnosis.is_confirmed is True
    assert diagnosis.evidence


def test_low_confidence_analysis_is_not_saved_as_fact() -> None:
    diagnosis = parse_error_analysis(
        {
            "category": "structural",
            "confidence": 0.4,
            "evidence": ["One ambiguous response"],
            "explanation": "This may be a missing prerequisite.",
        }
    )

    assert diagnosis.category is ErrorType.UNKNOWN
    assert diagnosis.is_confirmed is False


def test_malformed_analysis_falls_back_to_unknown() -> None:
    diagnosis = parse_error_analysis({"category": "invented", "confidence": "high"})

    assert diagnosis.category is ErrorType.UNKNOWN
    assert diagnosis.confidence == 0.0
