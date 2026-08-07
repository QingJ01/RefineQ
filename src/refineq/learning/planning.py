"""Deterministic learning-path construction for exams and open-ended capabilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from refineq.learning.evidence import stable_id
from refineq.learning.models import StudyPlan, StudySession

MAX_PLAN_DAYS = 365
ACTIVITY_SEQUENCE = ("learn", "practice", "apply", "review")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def build_study_plan(
    *,
    goal: str,
    topic_ids: list[str],
    exam_at: datetime,
    daily_minutes: int,
    start_at: datetime,
) -> StudyPlan:
    """Distribute varied learning activities across the available path."""

    start_at = _utc(start_at)
    exam_at = _utc(exam_at)
    if exam_at <= start_at:
        raise ValueError("exam_at must be later than start_at")

    topics = list(dict.fromkeys(topic.strip() for topic in topic_ids if topic.strip()))
    if not topics:
        raise ValueError("at least one topic is required")

    available_days = (exam_at.date() - start_at.date()).days
    if available_days < 1:
        raise ValueError("the plan requires at least one pre-exam study day")
    if available_days > MAX_PLAN_DAYS:
        raise ValueError(f"the plan horizon must not exceed {MAX_PLAN_DAYS} days")

    plan_id = stable_id(
        "plan",
        goal,
        exam_at.isoformat(),
        str(daily_minutes),
        *topics,
    )
    sessions = []
    for day_offset in range(available_days):
        planned_at = start_at + timedelta(days=day_offset)
        topic_id = topics[day_offset % len(topics)]
        activity = ACTIVITY_SEQUENCE[(day_offset // len(topics)) % len(ACTIVITY_SEQUENCE)]
        sessions.append(
            StudySession(
                id=stable_id("session", plan_id, planned_at.date().isoformat(), topic_id),
                topic_id=topic_id,
                planned_at=planned_at,
                minutes=daily_minutes,
                activity=activity,
            )
        )

    return StudyPlan(
        id=plan_id,
        goal=goal.strip(),
        exam_at=exam_at,
        daily_minutes=daily_minutes,
        sessions=sessions,
    )
