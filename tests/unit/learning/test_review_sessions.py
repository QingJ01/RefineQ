"""Tests for the review sessions used by the live learning plan."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from refineq.learning.models import StudySession
from refineq.learning.service import MAX_REVIEW_SESSIONS, _upsert_review_session

NOW = datetime(2026, 8, 8, 9, 0, tzinfo=UTC)


def test_upsert_review_session_deduplicates_topics_and_bounds_history() -> None:
    sessions = [
        StudySession(
            id=f"review_completed-{index}",
            topic_id=f"topic-{index}",
            planned_at=NOW - timedelta(days=30 - index),
            minutes=20,
            activity="review",
            status="completed",
        ).model_dump(mode="json")
        for index in range(MAX_REVIEW_SESSIONS + 3)
    ]
    sessions.extend(
        [
            StudySession(
                id="review_old-pending",
                topic_id="algebra",
                planned_at=NOW + timedelta(days=1),
                minutes=20,
                activity="review",
            ).model_dump(mode="json"),
            StudySession(
                id="session-plan-review",
                topic_id="algebra",
                planned_at=NOW + timedelta(days=2),
                minutes=20,
                activity="review",
            ).model_dump(mode="json"),
            StudySession(
                id="study-session",
                topic_id="algebra",
                planned_at=NOW,
                minutes=30,
                activity="practice",
            ).model_dump(mode="json"),
        ]
    )
    plan = {"sessions": sessions}
    replacement = StudySession(
        id="review_new-pending",
        topic_id="algebra",
        planned_at=NOW + timedelta(days=3),
        minutes=20,
        activity="review",
    )

    next_review_at = _upsert_review_session(plan, replacement)

    reviews = [item for item in plan["sessions"] if item["activity"] == "review"]
    pending_algebra = [
        item for item in reviews if item["topic_id"] == "algebra" and item["status"] != "completed"
    ]
    assert {item["id"] for item in pending_algebra} == {"session-plan-review"}
    assert next_review_at == NOW + timedelta(days=2)
    assert len([item for item in reviews if item["id"].startswith("review_")]) == (
        MAX_REVIEW_SESSIONS
    )
    assert any(item["id"] == "session-plan-review" for item in plan["sessions"])
    assert any(item["id"] == "study-session" for item in plan["sessions"])
