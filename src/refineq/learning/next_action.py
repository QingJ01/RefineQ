"""Deterministic, replayable selection of one workspace learning action."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from refineq.learning.models import StudyPlan

NextActionType = Literal[
    "upload_material",
    "start_review",
    "start_session",
    "repair_pace",
    "start_practice",
]
NextActionTrigger = Literal[
    "material_missing",
    "due_review",
    "scheduled_session",
    "pace_risk",
    "weak_topic",
]


class NextActionAlternative(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action_type: Literal["open_materials", "view_plan", "start_practice"]
    target_id: str | None = None


class NextAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    workspace_id: str
    version: int = Field(ge=1)
    expires_at: datetime
    action_type: NextActionType
    trigger: NextActionTrigger
    reason_code: str
    reason: str
    preconditions: dict[str, bool]
    evidence_refs: list[str]
    expected_outcome: str
    target_id: str | None = None
    topic_id: str | None = None
    minutes: int | None = Field(default=None, ge=0)
    alternatives: list[NextActionAlternative]
    risk_level: Literal["low", "medium", "high"] = "low"
    approval_mode: Literal["advise", "confirm", "auto_safe"] = "auto_safe"


def _stable_action_id(
    workspace_id: str,
    version: int,
    action_type: NextActionType,
    target_id: str | None,
) -> str:
    digest = sha256(
        f"{workspace_id}:{version}:{action_type}:{target_id or '-'}".encode()
    ).hexdigest()[:20]
    return f"next_{digest}"


def _local_date(value: datetime, timezone_offset_minutes: int):
    local_timezone = timezone(timedelta(minutes=timezone_offset_minutes))
    return value.astimezone(local_timezone).date()


def _base_action(
    *,
    workspace_id: str,
    version: int,
    now: datetime,
    action_type: NextActionType,
    trigger: NextActionTrigger,
    reason_code: str,
    reason: str,
    expected_outcome: str,
    target_id: str | None = None,
    topic_id: str | None = None,
    minutes: int | None = None,
    evidence_refs: list[str] | None = None,
    alternatives: list[NextActionAlternative] | None = None,
    has_searchable_material: bool,
    risk_level: Literal["low", "medium", "high"] = "low",
    approval_mode: Literal["advise", "confirm", "auto_safe"] = "auto_safe",
) -> NextAction:
    observed_at = now.astimezone(UTC)
    bucket_start = observed_at.replace(
        minute=observed_at.minute - observed_at.minute % 5,
        second=0,
        microsecond=0,
    )
    return NextAction(
        id=_stable_action_id(workspace_id, version, action_type, target_id),
        workspace_id=workspace_id,
        version=version,
        expires_at=bucket_start + timedelta(minutes=5),
        action_type=action_type,
        trigger=trigger,
        reason_code=reason_code,
        reason=reason,
        preconditions={"has_searchable_material": has_searchable_material},
        evidence_refs=evidence_refs or [],
        expected_outcome=expected_outcome,
        target_id=target_id,
        topic_id=topic_id,
        minutes=minutes,
        alternatives=alternatives
        or [NextActionAlternative(action_type="view_plan", target_id=target_id)],
        risk_level=risk_level,
        approval_mode=approval_mode,
    )


def select_next_action(
    *,
    workspace_id: str,
    version: int,
    plan: StudyPlan | None,
    material_statuses: list[str],
    mastery: dict[str, float],
    topic_names: dict[str, str],
    now: datetime,
    timezone_offset_minutes: int = 0,
) -> NextAction:
    """Select one action from a versioned snapshot without model judgment."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if not -14 * 60 <= timezone_offset_minutes <= 14 * 60:
        raise ValueError("timezone offset must be between UTC-14 and UTC+14")

    observed_at = now.astimezone(UTC)
    has_searchable_material = "indexed" in material_statuses
    if not has_searchable_material:
        return _base_action(
            workspace_id=workspace_id,
            version=version,
            now=observed_at,
            action_type="upload_material",
            trigger="material_missing",
            reason_code="material_required",
            reason="Upload a source before starting a grounded learning task.",
            expected_outcome="Unlock source-grounded questions and feedback.",
            alternatives=[NextActionAlternative(action_type="view_plan")],
            has_searchable_material=False,
        )

    sessions = [
        session for session in (plan.sessions if plan else []) if session.status != "completed"
    ]
    due_reviews = sorted(
        (
            session
            for session in sessions
            if session.activity == "review" and session.planned_at <= observed_at
        ),
        key=lambda session: (session.planned_at, session.id),
    )
    if due_reviews:
        review = due_reviews[0]
        return _base_action(
            workspace_id=workspace_id,
            version=version,
            now=observed_at,
            action_type="start_review",
            trigger="due_review",
            reason_code="review_due",
            reason=f"The review for {topic_names.get(review.topic_id, review.topic_id)} is due.",
            expected_outcome="Complete the oldest due review and refresh its evidence.",
            target_id=review.id,
            topic_id=review.topic_id,
            minutes=review.minutes,
            evidence_refs=[review.id],
            has_searchable_material=True,
        )

    local_today = _local_date(observed_at, timezone_offset_minutes)
    today_sessions = sorted(
        (
            session
            for session in sessions
            if _local_date(session.planned_at, timezone_offset_minutes) == local_today
        ),
        key=lambda session: (session.planned_at, session.id),
    )
    if today_sessions:
        session = today_sessions[0]
        return _base_action(
            workspace_id=workspace_id,
            version=version,
            now=observed_at,
            action_type="start_session",
            trigger="scheduled_session",
            reason_code="session_scheduled_today",
            reason=f"Today's plan schedules {topic_names.get(session.topic_id, session.topic_id)}.",
            expected_outcome="Complete the next scheduled learning session.",
            target_id=session.id,
            topic_id=session.topic_id,
            minutes=session.minutes,
            evidence_refs=[session.id],
            has_searchable_material=True,
        )

    if plan is not None and sessions:
        exam_date = _local_date(plan.exam_at, timezone_offset_minutes)
        remaining_days = max(0, (exam_date - local_today).days + 1)
        available_minutes = remaining_days * plan.daily_minutes
        remaining_minutes = sum(session.minutes for session in sessions)
        if remaining_minutes > available_minutes:
            return _base_action(
                workspace_id=workspace_id,
                version=version,
                now=observed_at,
                action_type="repair_pace",
                trigger="pace_risk",
                reason_code="plan_exceeds_capacity",
                reason="The remaining plan exceeds the time available before the target date.",
                expected_outcome="Review the plan before starting a lower-priority task.",
                target_id=plan.id,
                minutes=remaining_minutes,
                evidence_refs=[plan.id],
                has_searchable_material=True,
                risk_level="medium",
                approval_mode="advise",
            )

    weakest_topic = min(
        mastery,
        key=lambda topic_id: (mastery[topic_id], topic_id),
        default=(sessions[0].topic_id if sessions else None),
    )
    return _base_action(
        workspace_id=workspace_id,
        version=version,
        now=observed_at,
        action_type="start_practice",
        trigger="weak_topic",
        reason_code="weakest_topic",
        reason=(
            f"Practice {topic_names.get(weakest_topic, weakest_topic)} to reduce the largest gap."
            if weakest_topic
            else "Start a source-grounded practice task."
        ),
        expected_outcome="Create new evidence for the least-certain topic.",
        target_id=weakest_topic,
        topic_id=weakest_topic,
        evidence_refs=[weakest_topic] if weakest_topic else [],
        alternatives=[NextActionAlternative(action_type="view_plan")],
        has_searchable_material=True,
    )
