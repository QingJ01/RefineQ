"""Pure contracts for coach action extraction and server-side proposal resolution."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from threading import Event
from time import monotonic

import pytest
from pydantic import ValidationError

from refineq.agent.actions import (
    AdjustPracticeIntent,
    AdjustPracticeProposal,
    BoundedIntentExecutor,
    PlanSessionSelector,
    RejectedProposal,
    SaveQuestionIntent,
    SaveQuestionProposal,
    UpdatePlanSessionIntent,
    UpdatePlanSessionProposal,
    derive_action_id,
    resolve_action_proposal,
)
from refineq.learning.models import LearningMode

NOW = datetime(2026, 8, 8, 12, tzinfo=UTC)


def _progress() -> dict:
    return {
        "exam_at": "2026-08-20T12:00:00+00:00",
        "topics": {
            "cache": {"name": "Cache consistency"},
            "locks": {"name": "Locking"},
        },
        "bkt_states": {
            "cache": {"p_mastery": 0.6},
            "locks": {"p_mastery": 0.2},
        },
        "difficulty_states": {
            "cache": {"level": 3},
            "locks": {"level": 2},
        },
        "pending_question": {
            "id": "question-current",
            "topic_id": "cache",
            "difficulty_level": 3,
            "learning_mode": "case",
        },
        "plan": {
            "id": "plan-1",
            "goal": "Pass the exam",
            "exam_at": "2026-08-20T12:00:00+00:00",
            "daily_minutes": 45,
            "sessions": [
                {
                    "id": "session-recent",
                    "topic_id": "cache",
                    "planned_at": "2026-08-08T10:00:00+00:00",
                    "minutes": 30,
                    "activity": "review",
                    "status": "planned",
                },
                {
                    "id": "session-next",
                    "topic_id": "locks",
                    "planned_at": "2026-08-09T12:00:00+00:00",
                    "minutes": 30,
                    "activity": "practice",
                    "status": "planned",
                },
            ],
        },
    }


def _resolve(intent, *, progress: dict | None = None, timezone: str = "UTC"):
    return resolve_action_proposal(
        intent,
        progress=progress or _progress(),
        session_id="coach-session",
        turn_id="turn-1",
        timezone=timezone,
        now=NOW,
    )


def test_plan_intent_requires_a_mutation_and_consistent_selector_fields() -> None:
    with pytest.raises(ValidationError):
        UpdatePlanSessionIntent(
            type="update_plan_session",
            selector=PlanSessionSelector(when="next"),
        )

    with pytest.raises(ValidationError):
        PlanSessionSelector(when="on_relative_date")

    with pytest.raises(ValidationError):
        PlanSessionSelector(when="on_date", date="tomorrow")

    with pytest.raises(ValidationError):
        UpdatePlanSessionProposal(
            type="update_plan_session",
            action_id="action-1",
            session_id="session-1",
            session_label="Session 1",
        )


def test_action_id_hashes_the_complete_turn_identity() -> None:
    first = derive_action_id("coach-session", "turn-1", "adjust_practice")

    assert first == derive_action_id("coach-session", "turn-1", "adjust_practice")
    assert first != derive_action_id("coach-session", "turn-2", "adjust_practice")
    assert len(first) == 32
    assert set(first) <= set("0123456789abcdef")


def test_adjust_practice_inherits_the_pending_question_fields() -> None:
    proposal = _resolve(AdjustPracticeIntent(type="adjust_practice", difficulty="easier"))

    assert isinstance(proposal, AdjustPracticeProposal)
    assert proposal.topic_id == "cache"
    assert proposal.difficulty == 2
    assert proposal.learning_mode is LearningMode.CASE
    assert proposal.destructive is True


def test_adjust_practice_without_pending_question_falls_back_to_weakest_topic() -> None:
    progress = _progress()
    progress["pending_question"] = None

    proposal = _resolve(AdjustPracticeIntent(type="adjust_practice"), progress=progress)

    assert isinstance(proposal, AdjustPracticeProposal)
    assert proposal.topic_id == "locks"
    assert proposal.difficulty == 2
    assert proposal.learning_mode is LearningMode.CONCEPT
    assert proposal.destructive is False


def test_adjust_practice_rejects_unknown_topics_and_difficulty_boundaries() -> None:
    unknown = _resolve(AdjustPracticeIntent(type="adjust_practice", topic="Operating systems"))
    assert isinstance(unknown, RejectedProposal)
    assert unknown.reason_code == "unknown_topic"
    assert unknown.candidates == ["Cache consistency", "Locking"]

    progress = _progress()
    progress["pending_question"]["difficulty_level"] = 1
    bounded = _resolve(
        AdjustPracticeIntent(type="adjust_practice", difficulty="easier"),
        progress=progress,
    )
    assert isinstance(bounded, RejectedProposal)
    assert bounded.reason_code == "difficulty_at_bound"


def test_save_question_targets_only_the_current_pending_question() -> None:
    proposal = _resolve(SaveQuestionIntent(type="save_question", saved=True))
    assert isinstance(proposal, SaveQuestionProposal)
    assert proposal.question_id == "question-current"
    assert proposal.saved is True

    progress = _progress()
    progress["pending_question"] = None
    rejected = _resolve(
        SaveQuestionIntent(type="save_question", saved=False),
        progress=progress,
    )
    assert isinstance(rejected, RejectedProposal)
    assert rejected.reason_code == "no_pending_question"


@pytest.mark.parametrize(
    ("selector", "expected_session_id"),
    [
        (PlanSessionSelector(when="most_recent"), "session-recent"),
        (PlanSessionSelector(when="next"), "session-next"),
        (
            PlanSessionSelector(when="on_relative_date", relative_date="tomorrow"),
            "session-next",
        ),
        (PlanSessionSelector(when="on_date", date="2026-08-09"), "session-next"),
    ],
)
def test_plan_selectors_resolve_against_server_time(
    selector: PlanSessionSelector,
    expected_session_id: str,
) -> None:
    proposal = _resolve(
        UpdatePlanSessionIntent(
            type="update_plan_session",
            selector=selector,
            mark_completed=True,
        )
    )

    assert isinstance(proposal, UpdatePlanSessionProposal)
    assert proposal.session_id == expected_session_id
    assert proposal.status == "completed"


def test_plan_date_selection_rejects_ambiguity_with_candidates() -> None:
    progress = _progress()
    duplicate = dict(progress["plan"]["sessions"][1])
    duplicate["id"] = "session-next-2"
    duplicate["topic_id"] = "cache"
    progress["plan"]["sessions"].append(duplicate)

    proposal = _resolve(
        UpdatePlanSessionIntent(
            type="update_plan_session",
            selector=PlanSessionSelector(
                when="on_relative_date",
                relative_date="tomorrow",
            ),
            mark_completed=True,
        ),
        progress=progress,
    )

    assert isinstance(proposal, RejectedProposal)
    assert proposal.reason_code == "ambiguous_session"
    assert len(proposal.candidates) == 2


def test_plan_move_preserves_local_time_and_rejects_exam_overflow() -> None:
    progress = _progress()
    progress["plan"]["sessions"][1]["planned_at"] = "2026-08-09T03:00:00+00:00"
    intent = UpdatePlanSessionIntent(
        type="update_plan_session",
        selector=PlanSessionSelector(when="next"),
        move_to_weekday="saturday",
    )

    proposal = _resolve(intent, progress=progress, timezone="Asia/Shanghai")

    assert isinstance(proposal, UpdatePlanSessionProposal)
    assert proposal.planned_at is not None
    assert proposal.planned_at.astimezone().tzinfo is not None
    local = proposal.planned_at.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Shanghai"))
    assert local.date().isoformat() == "2026-08-15"
    assert (local.hour, local.minute) == (11, 0)

    progress["plan"]["exam_at"] = "2026-08-10T12:00:00+00:00"
    rejected = _resolve(intent, progress=progress, timezone="Asia/Shanghai")
    assert isinstance(rejected, RejectedProposal)
    assert rejected.reason_code == "date_after_exam"


def test_plan_move_uses_the_learners_timezone_for_relative_weekdays() -> None:
    progress = _progress()
    progress["plan"]["sessions"][1]["planned_at"] = "2026-08-09T03:00:00+00:00"
    intent = UpdatePlanSessionIntent(
        type="update_plan_session",
        selector=PlanSessionSelector(when="next"),
        move_to_weekday="saturday",
    )

    shanghai = _resolve(intent, progress=progress, timezone="Asia/Shanghai")
    los_angeles = _resolve(intent, progress=progress, timezone="America/Los_Angeles")

    assert isinstance(shanghai, UpdatePlanSessionProposal)
    assert isinstance(los_angeles, UpdatePlanSessionProposal)
    assert shanghai.planned_at != los_angeles.planned_at


def test_bounded_intent_executor_rejects_work_instead_of_queueing(caplog) -> None:
    executor = BoundedIntentExecutor(max_workers=1)
    started = Event()
    release = Event()

    def block() -> str:
        started.set()
        release.wait(timeout=2)
        return "first"

    first = executor.submit(block)
    assert first is not None
    assert started.wait(timeout=1)

    observed_at = monotonic()
    with caplog.at_level(logging.WARNING):
        assert executor.submit(lambda: "queued") is None
    assert monotonic() - observed_at < 0.1
    assert "event=intent_extraction_skipped reason=capacity" in caplog.text

    release.set()
    assert first.result(timeout=1) == "first"
    admitted = executor.submit(lambda: "next")
    assert admitted is not None
    assert admitted.result(timeout=1) == "next"
