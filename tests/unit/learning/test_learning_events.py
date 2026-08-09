from datetime import UTC, datetime, timedelta

from refineq.learning.events import (
    MAX_JOURNEY_EVENTS,
    JourneyEvent,
    append_journey_event,
    build_journey_event,
    learning_journey_metrics,
)

START = datetime(2026, 8, 3, tzinfo=UTC)


def _event(
    workspace_id: str,
    name: str,
    minute: int,
    *,
    key: str | None = None,
    ref_id: str | None = None,
) -> JourneyEvent:
    return build_journey_event(
        workspace_id=workspace_id,
        name=name,
        idempotency_key=key or f"{name}-{minute}",
        occurred_at=START + timedelta(minutes=minute),
        ref_id=ref_id,
    )


def test_journey_events_are_idempotent_and_bounded() -> None:
    progress: dict = {}
    duplicate = _event("workspace-1", "workspace_opened", 0, key="same-open")

    assert append_journey_event(progress, duplicate) is True
    assert append_journey_event(progress, duplicate) is False
    for index in range(MAX_JOURNEY_EVENTS + 10):
        append_journey_event(
            progress,
            _event("workspace-1", "question_started", index + 1),
        )

    events = progress["journey_events"]
    assert len(events) == MAX_JOURNEY_EVENTS
    assert len({item["id"] for item in events}) == MAX_JOURNEY_EVENTS
    assert events[0]["occurred_at"] < events[-1]["occurred_at"]


def test_learning_metrics_are_computable_from_internal_events() -> None:
    records = [
        (
            "learner-a",
            "workspace-a",
            [
                _event("workspace-a", "intent_submitted", 0),
                _event("workspace-a", "workspace_ready", 1),
                _event("workspace-a", "workspace_opened", 2, key="open-day-1"),
                _event("workspace-a", "grounded_grade_created", 60, ref_id="attempt-a"),
                _event("workspace-a", "grounded_grade_shown", 61, ref_id="attempt-a"),
                _event("workspace-a", "workspace_opened", 120, key="open-day-2"),
                _event("workspace-a", "question_started", 150, ref_id="question-a"),
            ],
        ),
        (
            "learner-b",
            "workspace-b",
            [_event("workspace-b", "workspace_opened", 30)],
        ),
        (
            "outside-window",
            "workspace-c",
            [
                build_journey_event(
                    workspace_id="workspace-c",
                    name="grounded_grade_shown",
                    idempotency_key="old",
                    occurred_at=START - timedelta(days=1),
                    ref_id="attempt-c",
                )
            ],
        ),
    ]

    metrics = learning_journey_metrics(
        records,
        starts_at=START,
        ends_at=START + timedelta(days=7),
    )

    assert metrics["weekly_active_learners"] == 2
    assert metrics["grounded_loop_completers"] == 1
    assert metrics["grounded_loop_completion_rate"] == 0.5
    assert metrics["intent_to_grounded_grade_seconds"] == {
        "sample_size": 1,
        "p50": 3600.0,
        "p90": 3600.0,
    }
    assert metrics["revisit_open_to_question_seconds"] == {
        "sample_size": 1,
        "p50": 1800.0,
        "p90": 1800.0,
    }
