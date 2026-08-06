"""Tests for stable plans and evidence-backed recommendations."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from refineq.learning.evidence import create_evidence, make_recommendation
from refineq.learning.planning import build_study_plan

START = datetime(2026, 8, 6, 8, 0, tzinfo=UTC)
EXAM = datetime(2026, 8, 10, 8, 0, tzinfo=UTC)


def test_evidence_ids_are_idempotent_for_one_source_event() -> None:
    first = create_evidence(
        kind="attempt",
        source_id="attempt-42",
        summary="Chain-rule question answered incorrectly.",
        observed_at=START,
    )
    retried = create_evidence(
        kind="attempt",
        source_id="attempt-42",
        summary="Chain-rule question answered incorrectly.",
        observed_at=START,
    )

    assert first.id == retried.id


def test_recommendation_must_cite_learning_evidence() -> None:
    with pytest.raises(ValueError, match="evidence"):
        make_recommendation(
            action="Review the chain rule",
            rationale="Recent mistakes show a gap.",
            evidence=[],
        )


def test_recommendation_carries_evidence_ids() -> None:
    evidence = create_evidence(
        kind="attempt",
        source_id="attempt-42",
        summary="Chain-rule question answered incorrectly.",
        observed_at=START,
    )

    recommendation = make_recommendation(
        action="Review the chain rule",
        rationale="A recent attempt exposed an application gap.",
        evidence=[evidence],
    )

    assert recommendation.evidence_ids == [evidence.id]


def test_study_plan_and_session_ids_are_stable() -> None:
    inputs = {
        "goal": "Pass the calculus final",
        "topic_ids": ["limits", "derivatives"],
        "exam_at": EXAM,
        "daily_minutes": 45,
        "start_at": START,
    }

    first = build_study_plan(**inputs)
    second = build_study_plan(**inputs)

    assert first.id == second.id
    assert [session.id for session in first.sessions] == [
        session.id for session in second.sessions
    ]
    assert len(first.sessions) == 4
    assert {session.topic_id for session in first.sessions} == {"limits", "derivatives"}


def test_study_plan_rejects_naive_exam_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_study_plan(
            goal="Pass the calculus final",
            topic_ids=["limits"],
            exam_at=datetime(2026, 8, 10, 8, 0),
            daily_minutes=45,
            start_at=START,
        )
