"""Context-isolated coach intents and deterministic server-side action proposals."""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from hashlib import blake2b
from threading import BoundedSemaphore
from typing import Annotated, Any, Literal, TypeAlias, TypeVar
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

from refineq.learning.models import LearningMode

logger = logging.getLogger(__name__)

Weekday = Literal[
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
RelativeDate = Literal["today", "tomorrow"]
ActionType = Literal["adjust_practice", "update_plan_session", "save_question"]

_WEEKDAY_INDEX: dict[str, int] = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


class AdjustPracticeIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["adjust_practice"]
    topic: str | None = Field(default=None, min_length=1, max_length=200)
    difficulty: Literal["easier", "harder"] | None = None
    learning_mode: LearningMode | None = None


class PlanSessionSelector(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    when: Literal["most_recent", "next", "on_relative_date", "on_date"]
    relative_date: RelativeDate | None = None
    date: str | None = None
    topic: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_selector(self) -> PlanSessionSelector:
        if self.when == "on_relative_date":
            if self.relative_date is None or self.date is not None:
                raise ValueError("relative_date is required only for on_relative_date")
        elif self.when == "on_date":
            if self.date is None or self.relative_date is not None:
                raise ValueError("date is required only for on_date")
            try:
                date.fromisoformat(self.date)
            except ValueError as error:
                raise ValueError("date must use YYYY-MM-DD") from error
        elif self.relative_date is not None or self.date is not None:
            raise ValueError("date selectors are not valid for this selector")
        return self


class UpdatePlanSessionIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["update_plan_session"]
    selector: PlanSessionSelector
    mark_completed: bool | None = None
    move_to_weekday: Weekday | None = None
    move_to_relative_date: RelativeDate | None = None
    move_to_date: str | None = None

    @model_validator(mode="after")
    def validate_mutation(self) -> UpdatePlanSessionIntent:
        moves = [
            self.move_to_weekday,
            self.move_to_relative_date,
            self.move_to_date,
        ]
        if self.mark_completed is None and not any(value is not None for value in moves):
            raise ValueError("a plan action must update status or date")
        if sum(value is not None for value in moves) > 1:
            raise ValueError("plan move targets are mutually exclusive")
        if self.move_to_date is not None:
            try:
                date.fromisoformat(self.move_to_date)
            except ValueError as error:
                raise ValueError("move_to_date must use YYYY-MM-DD") from error
        return self


class SaveQuestionIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["save_question"]
    saved: bool


CoachIntent: TypeAlias = Annotated[
    AdjustPracticeIntent | UpdatePlanSessionIntent | SaveQuestionIntent,
    Field(discriminator="type"),
]


class IntentExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: CoachIntent | None = None


class AdjustPracticeProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["adjust_practice"]
    action_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    topic_id: str
    topic_name: str
    difficulty: int = Field(ge=1, le=5)
    learning_mode: LearningMode
    destructive: bool
    expected_state_version: int = Field(ge=0)


class UpdatePlanSessionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["update_plan_session"]
    action_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    session_id: str
    session_label: str
    status: Literal["planned", "completed"] | None = None
    planned_at: datetime | None = None

    @model_validator(mode="after")
    def validate_result(self) -> UpdatePlanSessionProposal:
        if self.status is None and self.planned_at is None:
            raise ValueError("a plan proposal must update status or date")
        return self


class SaveQuestionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["save_question"]
    action_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    question_id: str
    saved: bool


class RejectedProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["rejected"] = "rejected"
    reason_code: str
    summary: str
    candidates: list[str] = Field(default_factory=list)


ActionProposal: TypeAlias = Annotated[
    AdjustPracticeProposal | UpdatePlanSessionProposal | SaveQuestionProposal | RejectedProposal,
    Field(discriminator="type"),
]


def derive_action_id(session_id: str, turn_id: str, action_type: ActionType) -> str:
    raw = f"{session_id}:{turn_id}:{action_type}".encode()
    return blake2b(raw, digest_size=16).hexdigest()


def _topic_name(topic_id: str, topic: Any) -> str:
    if isinstance(topic, dict) and isinstance(topic.get("name"), str):
        return topic["name"]
    if isinstance(topic, str):
        return topic
    return topic_id


def _topic_candidates(progress: dict[str, Any]) -> list[tuple[str, str]]:
    topics = progress.get("topics", {})
    if not isinstance(topics, dict):
        return []
    return [(topic_id, _topic_name(topic_id, topic)) for topic_id, topic in topics.items()]


def _reject(reason_code: str, summary: str, candidates: list[str] | None = None):
    return RejectedProposal(
        reason_code=reason_code,
        summary=summary,
        candidates=candidates or [],
    )


def _resolve_adjust(
    intent: AdjustPracticeIntent,
    *,
    progress: dict[str, Any],
    action_id: str,
    expected_state_version: int,
) -> ActionProposal:
    topics = _topic_candidates(progress)
    if not topics:
        return _reject("no_topics", "This learning space has no practice topics.")
    pending = progress.get("pending_question")
    pending = pending if isinstance(pending, dict) else None

    if intent.topic is not None:
        normalized = intent.topic.strip().casefold()
        matches = [
            (topic_id, name)
            for topic_id, name in topics
            if normalized in {topic_id.casefold(), name.casefold()}
        ]
        if len(matches) != 1:
            return _reject(
                "unknown_topic",
                f'This learning space has no topic named "{intent.topic}".',
                sorted(name for _, name in topics),
            )
        topic_id, topic_name = matches[0]
    elif pending is not None and isinstance(pending.get("topic_id"), str):
        topic_id = pending["topic_id"]
        topic_name = dict(topics).get(topic_id, topic_id)
    else:
        states = progress.get("bkt_states", {})

        def mastery(item: tuple[str, str]) -> tuple[float, str]:
            state = states.get(item[0], {}) if isinstance(states, dict) else {}
            score = state.get("p_mastery", 1.0) if isinstance(state, dict) else 1.0
            return float(score), item[0]

        topic_id, topic_name = min(topics, key=mastery)

    if pending is not None and pending.get("topic_id") == topic_id:
        base_difficulty = int(pending.get("difficulty_level", 2))
    else:
        difficulty_states = progress.get("difficulty_states", {})
        state = difficulty_states.get(topic_id, {}) if isinstance(difficulty_states, dict) else {}
        base_difficulty = int(state.get("level", 2)) if isinstance(state, dict) else 2
    difficulty = base_difficulty
    if intent.difficulty == "easier":
        if base_difficulty <= 1:
            return _reject("difficulty_at_bound", "The current difficulty is already 1.")
        difficulty -= 1
    elif intent.difficulty == "harder":
        if base_difficulty >= 5:
            return _reject("difficulty_at_bound", "The current difficulty is already 5.")
        difficulty += 1

    if intent.learning_mode is not None:
        learning_mode = intent.learning_mode
    elif pending is not None and pending.get("topic_id") == topic_id:
        learning_mode = LearningMode(pending.get("learning_mode", LearningMode.CONCEPT))
    else:
        learning_mode = LearningMode.CONCEPT

    return AdjustPracticeProposal(
        type="adjust_practice",
        action_id=action_id,
        topic_id=topic_id,
        topic_name=topic_name,
        difficulty=difficulty,
        learning_mode=learning_mode,
        destructive=pending is not None,
        expected_state_version=expected_state_version,
    )


def _parse_aware(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return parsed


def _session_label(
    session: dict[str, Any],
    *,
    zone: ZoneInfo,
    topics: dict[str, str],
) -> str:
    planned = _parse_aware(session["planned_at"]).astimezone(zone)
    topic = topics.get(str(session.get("topic_id")), str(session.get("topic_id", "")))
    activity = str(session.get("activity", "practice"))
    return f"{planned:%Y-%m-%d %H:%M} · {topic} · {activity}"


def _select_plan_session(
    selector: PlanSessionSelector,
    *,
    sessions: list[dict[str, Any]],
    topics: dict[str, str],
    zone: ZoneInfo,
    now: datetime,
) -> dict[str, Any] | RejectedProposal:
    candidates = sessions
    if selector.topic is not None:
        normalized = selector.topic.strip().casefold()
        candidates = [
            session
            for session in candidates
            if normalized
            in {
                str(session.get("topic_id", "")).casefold(),
                topics.get(str(session.get("topic_id", "")), "").casefold(),
            }
        ]

    parsed = [(session, _parse_aware(session["planned_at"])) for session in candidates]
    local_now = now.astimezone(zone)
    if selector.when == "most_recent":
        eligible = [(session, planned) for session, planned in parsed if planned <= now]
        if eligible:
            selected_time = max(planned for _, planned in eligible)
            matches = [session for session, planned in eligible if planned == selected_time]
        else:
            matches = []
    elif selector.when == "next":
        eligible = [(session, planned) for session, planned in parsed if planned > now]
        if eligible:
            selected_time = min(planned for _, planned in eligible)
            matches = [session for session, planned in eligible if planned == selected_time]
        else:
            matches = []
    else:
        target_date = (
            local_now.date() + timedelta(days=selector.relative_date == "tomorrow")
            if selector.when == "on_relative_date"
            else date.fromisoformat(selector.date or "")
        )
        matches = [
            session for session, planned in parsed if planned.astimezone(zone).date() == target_date
        ]

    labels = [_session_label(session, zone=zone, topics=topics) for session in matches]
    if not matches:
        return _reject("no_matching_session", "No study session matches that description.")
    if len(matches) > 1:
        return _reject(
            "ambiguous_session",
            "More than one study session matches that description.",
            labels,
        )
    return matches[0]


def _resolve_plan(
    intent: UpdatePlanSessionIntent,
    *,
    progress: dict[str, Any],
    action_id: str,
    timezone: str,
    now: datetime,
) -> ActionProposal:
    plan = progress.get("plan")
    if not isinstance(plan, dict) or not isinstance(plan.get("sessions"), list):
        return _reject("no_study_plan", "This learning space has no study plan.")
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return _reject("invalid_timezone", "The browser timezone is not valid.")
    topics = dict(_topic_candidates(progress))
    try:
        selected = _select_plan_session(
            intent.selector,
            sessions=plan["sessions"],
            topics=topics,
            zone=zone,
            now=now,
        )
    except (KeyError, TypeError, ValueError):
        return _reject("invalid_plan", "The study plan contains an invalid session.")
    if isinstance(selected, RejectedProposal):
        return selected

    planned_at: datetime | None = None
    if any(
        value is not None
        for value in (
            intent.move_to_weekday,
            intent.move_to_relative_date,
            intent.move_to_date,
        )
    ):
        local_now = now.astimezone(zone)
        selected_local = _parse_aware(selected["planned_at"]).astimezone(zone)
        if intent.move_to_weekday is not None:
            target_weekday = _WEEKDAY_INDEX[intent.move_to_weekday]
            offset = (target_weekday - local_now.weekday()) % 7 or 7
            target_date = local_now.date() + timedelta(days=offset)
        elif intent.move_to_relative_date is not None:
            target_date = local_now.date() + timedelta(
                days=intent.move_to_relative_date == "tomorrow"
            )
        else:
            target_date = date.fromisoformat(intent.move_to_date or "")

        if target_date < local_now.date():
            return _reject("date_before_today", "The target date is before today.")
        try:
            exam_at = _parse_aware(plan.get("exam_at") or progress["exam_at"])
        except (KeyError, TypeError, ValueError):
            return _reject("invalid_exam_date", "The exam date is not valid.")
        if target_date > exam_at.astimezone(zone).date():
            return _reject("date_after_exam", "The target date is after the exam.")
        planned_at = selected_local.replace(
            year=target_date.year,
            month=target_date.month,
            day=target_date.day,
        ).astimezone(UTC)

    status = None
    if intent.mark_completed is not None:
        status = "completed" if intent.mark_completed else "planned"
    return UpdatePlanSessionProposal(
        type="update_plan_session",
        action_id=action_id,
        session_id=str(selected["id"]),
        session_label=_session_label(selected, zone=zone, topics=topics),
        status=status,
        planned_at=planned_at,
    )


def resolve_action_proposal(
    intent: CoachIntent,
    *,
    progress: dict[str, Any],
    session_id: str,
    turn_id: str,
    timezone: str,
    expected_state_version: int,
    now: datetime | None = None,
) -> ActionProposal:
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    action_id = derive_action_id(session_id, turn_id, intent.type)
    if isinstance(intent, AdjustPracticeIntent):
        return _resolve_adjust(
            intent,
            progress=progress,
            action_id=action_id,
            expected_state_version=expected_state_version,
        )
    if isinstance(intent, SaveQuestionIntent):
        pending = progress.get("pending_question")
        if not isinstance(pending, dict) or not isinstance(pending.get("id"), str):
            return _reject("no_pending_question", "There is no current question to save.")
        return SaveQuestionProposal(
            type="save_question",
            action_id=action_id,
            question_id=pending["id"],
            saved=intent.saved,
        )
    return _resolve_plan(
        intent,
        progress=progress,
        action_id=action_id,
        timezone=timezone,
        now=observed_at,
    )


T = TypeVar("T")


class BoundedIntentExecutor:
    """Execute short intent calls only when a worker is immediately available."""

    def __init__(self, *, max_workers: int = 4) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._permits = BoundedSemaphore(max_workers)

    def submit(self, operation: Callable[[], T]) -> Future[T] | None:
        if not self._permits.acquire(blocking=False):
            logger.warning(
                "event=intent_extraction_skipped reason=capacity duration_ms=0 mode=async"
            )
            return None

        def run() -> T:
            try:
                return operation()
            finally:
                self._permits.release()

        try:
            return self._executor.submit(run)
        except BaseException:
            self._permits.release()
            raise
