"""Tests for timezone-safe spaced review scheduling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from refineq.learning.models import KnowledgeType, ReviewRating, ReviewState
from refineq.learning.review import create_review_task, schedule_review

NOW = datetime(2026, 8, 6, 9, 0, tzinfo=UTC)


def test_review_task_ids_are_stable_across_retries() -> None:
    first = create_review_task(
        owner_id="owner",
        knowledge_point_id="calculus-chain-rule",
        knowledge_type=KnowledgeType.PROCEDURE,
        now=NOW,
    )
    second = create_review_task(
        owner_id="owner",
        knowledge_point_id="calculus-chain-rule",
        knowledge_type=KnowledgeType.PROCEDURE,
        now=NOW + timedelta(seconds=5),
    )

    assert first.id == second.id
    assert first.state.due_at.tzinfo is not None


def test_good_review_schedules_an_aware_future_date() -> None:
    state = ReviewState(
        knowledge_point_id="kp-1",
        due_at=NOW,
        interval_days=0,
    )

    updated = schedule_review(state, ReviewRating.GOOD, reviewed_at=NOW)

    assert updated.due_at == NOW + timedelta(days=1)
    assert updated.due_at.utcoffset() == timedelta(0)
    assert updated.streak == 1


def test_naive_review_dates_are_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        ReviewState(
            knowledge_point_id="kp-1",
            due_at=datetime(2026, 8, 6, 9, 0),
        )
