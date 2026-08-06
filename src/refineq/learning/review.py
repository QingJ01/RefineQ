"""Timezone-safe deterministic spaced-review policy."""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from refineq.learning.evidence import stable_id
from refineq.learning.models import (
    KnowledgeType,
    ReviewRating,
    ReviewState,
    ReviewTask,
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def create_review_task(
    *,
    owner_id: str,
    knowledge_point_id: str,
    knowledge_type: KnowledgeType,
    now: datetime,
) -> ReviewTask:
    """Create one stable queue identity per owner and knowledge point."""

    due_at = _utc(now)
    return ReviewTask(
        id=stable_id("review", owner_id, knowledge_point_id),
        owner_id=owner_id,
        knowledge_point_id=knowledge_point_id,
        knowledge_type=knowledge_type,
        state=ReviewState(knowledge_point_id=knowledge_point_id, due_at=due_at),
    )


def schedule_review(
    state: ReviewState,
    rating: ReviewRating,
    *,
    reviewed_at: datetime,
) -> ReviewState:
    """Schedule the next review using transparent deterministic intervals."""

    reviewed_at = _utc(reviewed_at)
    if rating is ReviewRating.AGAIN:
        return state.model_copy(
            update={
                "due_at": reviewed_at + timedelta(minutes=10),
                "interval_days": 0,
                "streak": 0,
                "lapses": state.lapses + 1,
            }
        )

    base = max(1, state.interval_days)
    if rating is ReviewRating.HARD:
        interval_days = max(1, math.ceil(base * 1.2))
    elif rating is ReviewRating.GOOD:
        interval_days = 1 if state.interval_days == 0 else base * 2
    else:
        interval_days = 3 if state.interval_days == 0 else base * 3

    return state.model_copy(
        update={
            "due_at": reviewed_at + timedelta(days=interval_days),
            "interval_days": interval_days,
            "streak": state.streak + 1,
        }
    )


def due_review_tasks(
    tasks: Iterable[ReviewTask],
    *,
    now: datetime,
    limit: int = 20,
) -> list[ReviewTask]:
    """Return due work in chronological, deterministic order."""

    now = _utc(now)
    due = [task for task in tasks if task.state.due_at <= now]
    return sorted(due, key=lambda task: (task.state.due_at, task.id))[:limit]
