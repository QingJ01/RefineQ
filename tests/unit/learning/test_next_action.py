from datetime import UTC, datetime, timedelta

import pytest

from refineq.learning.models import StudyPlan, StudySession
from refineq.learning.next_action import select_next_action

NOW = datetime(2026, 8, 9, 2, 0, tzinfo=UTC)


def _plan(
    *sessions: StudySession,
    exam_at: datetime | None = None,
    daily_minutes: int = 45,
) -> StudyPlan:
    return StudyPlan(
        id="plan-1",
        goal="Pass calculus",
        exam_at=exam_at or NOW + timedelta(days=10),
        daily_minutes=daily_minutes,
        sessions=list(sessions)
        or [
            StudySession(
                id="future-session",
                topic_id="limits",
                planned_at=NOW + timedelta(days=2),
                minutes=30,
            )
        ],
    )


def _select(
    *,
    plan: StudyPlan | None = None,
    material_statuses: list[str] | None = None,
    mastery: dict[str, float] | None = None,
):
    return select_next_action(
        workspace_id="workspace-1",
        version=7,
        plan=plan or _plan(),
        material_statuses=material_statuses if material_statuses is not None else ["indexed"],
        mastery=mastery or {"limits": 0.4, "derivatives": 0.2},
        topic_names={"limits": "Limits", "derivatives": "Derivatives"},
        now=NOW,
        timezone_offset_minutes=480,
    )


@pytest.mark.parametrize("material_statuses", [[], ["processing"], ["failed"]])
def test_material_gate_precedes_due_reviews_and_plan_sessions(
    material_statuses: list[str],
) -> None:
    due_review = StudySession(
        id="review-due",
        topic_id="limits",
        planned_at=NOW - timedelta(hours=1),
        minutes=20,
        activity="review",
    )
    today_session = StudySession(
        id="today-session",
        topic_id="derivatives",
        planned_at=NOW + timedelta(hours=2),
        minutes=30,
    )

    action = _select(
        plan=_plan(due_review, today_session),
        material_statuses=material_statuses,
    )

    assert action.action_type == "upload_material"
    assert action.trigger == "material_missing"
    assert action.target_id is None
    assert action.preconditions == {"has_searchable_material": False}
    assert action.evidence_refs == []


def test_due_review_precedes_today_session() -> None:
    due_review = StudySession(
        id="review-due",
        topic_id="limits",
        planned_at=NOW - timedelta(hours=1),
        minutes=20,
        activity="review",
    )
    today_session = StudySession(
        id="today-session",
        topic_id="derivatives",
        planned_at=NOW + timedelta(hours=2),
        minutes=30,
    )

    action = _select(plan=_plan(today_session, due_review))

    assert action.action_type == "start_review"
    assert action.trigger == "due_review"
    assert action.target_id == "review-due"
    assert action.topic_id == "limits"
    assert action.evidence_refs == ["review-due"]


def test_local_today_session_precedes_pace_risk() -> None:
    # 02:00 UTC is 10:00 for the supplied UTC+8 offset.
    today_session = StudySession(
        id="today-session",
        topic_id="derivatives",
        planned_at=NOW + timedelta(hours=8),
        minutes=90,
    )

    action = _select(
        plan=_plan(
            today_session,
            exam_at=NOW + timedelta(hours=20),
            daily_minutes=30,
        )
    )

    assert action.action_type == "start_session"
    assert action.trigger == "scheduled_session"
    assert action.target_id == "today-session"
    assert action.topic_id == "derivatives"


def test_future_review_today_is_still_a_today_session() -> None:
    future_review = StudySession(
        id="review-later-today",
        topic_id="limits",
        planned_at=NOW + timedelta(hours=4),
        minutes=20,
        activity="review",
    )

    action = _select(plan=_plan(future_review))

    assert action.action_type == "start_session"
    assert action.trigger == "scheduled_session"
    assert action.target_id == "review-later-today"


def test_deadline_capacity_risk_precedes_weak_topic_practice() -> None:
    future = StudySession(
        id="future-session",
        topic_id="limits",
        planned_at=NOW + timedelta(days=2),
        minutes=120,
    )

    action = _select(
        plan=_plan(
            future,
            exam_at=NOW + timedelta(hours=20),
            daily_minutes=30,
        )
    )

    assert action.action_type == "repair_pace"
    assert action.trigger == "pace_risk"
    assert action.target_id == "plan-1"
    assert action.minutes == 120
    assert action.evidence_refs == ["plan-1"]


def test_past_deadline_has_zero_remaining_capacity() -> None:
    overdue = StudySession(
        id="overdue-session",
        topic_id="limits",
        planned_at=NOW + timedelta(days=2),
        minutes=15,
    )

    action = _select(
        plan=_plan(
            overdue,
            exam_at=NOW - timedelta(days=1),
            daily_minutes=30,
        )
    )

    assert action.action_type == "repair_pace"
    assert action.trigger == "pace_risk"


def test_weakest_topic_is_the_grounded_practice_fallback() -> None:
    action = _select(mastery={"limits": 0.6, "derivatives": 0.15})

    assert action.action_type == "start_practice"
    assert action.trigger == "weak_topic"
    assert action.target_id == "derivatives"
    assert action.topic_id == "derivatives"
    assert action.evidence_refs == ["derivatives"]


def test_same_snapshot_produces_the_same_stable_decision() -> None:
    first = _select()
    second = _select()

    assert first == second
    assert first.id == second.id
    assert first.version == 7
    assert first.preconditions == {"has_searchable_material": True}
