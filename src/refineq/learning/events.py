"""Bounded product-journey events and internally computable learning metrics."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from hashlib import sha256
from math import ceil
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator

MAX_JOURNEY_EVENTS = 500
JourneyEventName = Literal[
    "intent_submitted",
    "workspace_ready",
    "workspace_opened",
    "material_searchable",
    "question_started",
    "grounded_grade_created",
    "grounded_grade_shown",
]


class JourneyEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    workspace_id: str
    name: JourneyEventName
    occurred_at: datetime
    ref_id: str | None = None

    @field_validator("occurred_at", mode="after")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value.astimezone(UTC)


def build_journey_event(
    *,
    workspace_id: str,
    name: JourneyEventName,
    idempotency_key: str,
    occurred_at: datetime,
    ref_id: str | None = None,
) -> JourneyEvent:
    digest = sha256(
        f"{workspace_id}:{name}:{idempotency_key}".encode()
    ).hexdigest()[:24]
    return JourneyEvent(
        id=f"journey_{digest}",
        workspace_id=workspace_id,
        name=name,
        occurred_at=occurred_at,
        ref_id=ref_id,
    )


def append_journey_event(progress: dict[str, Any], event: JourneyEvent) -> bool:
    events = progress.setdefault("journey_events", [])
    if any(item.get("id") == event.id for item in events):
        return False
    events.append(event.model_dump(mode="json"))
    events.sort(key=lambda item: (item["occurred_at"], item["id"]))
    if len(events) > MAX_JOURNEY_EVENTS:
        del events[: len(events) - MAX_JOURNEY_EVENTS]
    return True


def _percentiles(values: list[float]) -> dict[str, int | float | None]:
    if not values:
        return {"sample_size": 0, "p50": None, "p90": None}
    ordered = sorted(values)

    def nearest_rank(percent: float) -> float:
        return ordered[max(0, ceil(percent * len(ordered)) - 1)]

    return {
        "sample_size": len(ordered),
        "p50": nearest_rank(0.5),
        "p90": nearest_rank(0.9),
    }


def learning_journey_metrics(
    records: Iterable[tuple[str, str, Iterable[JourneyEvent | dict[str, Any]]]],
    *,
    starts_at: datetime,
    ends_at: datetime,
) -> dict[str, Any]:
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise ValueError("starts_at must be timezone-aware")
    if ends_at.tzinfo is None or ends_at.utcoffset() is None:
        raise ValueError("ends_at must be timezone-aware")
    starts_at = starts_at.astimezone(UTC)
    ends_at = ends_at.astimezone(UTC)
    if starts_at >= ends_at:
        raise ValueError("starts_at must precede ends_at")

    active: set[str] = set()
    completers: set[str] = set()
    intent_durations: list[float] = []
    revisit_durations: list[float] = []

    for owner_id, _workspace_id, raw_events in records:
        events = sorted(
            (JourneyEvent.model_validate(item) for item in raw_events),
            key=lambda event: (event.occurred_at, event.id),
        )
        visible = [event for event in events if starts_at <= event.occurred_at < ends_at]
        if visible:
            active.add(owner_id)
        if any(event.name == "grounded_grade_shown" for event in visible):
            completers.add(owner_id)

        intents = [event for event in visible if event.name == "intent_submitted"]
        for intent in intents[:1]:
            grade = next(
                (
                    event
                    for event in events
                    if event.name == "grounded_grade_created"
                    and intent.occurred_at <= event.occurred_at < ends_at
                ),
                None,
            )
            if grade is not None:
                intent_durations.append((grade.occurred_at - intent.occurred_at).total_seconds())

        opens = [event for event in events if event.name == "workspace_opened"]
        for opened in opens[1:]:
            if not starts_at <= opened.occurred_at < ends_at:
                continue
            question = next(
                (
                    event
                    for event in events
                    if event.name == "question_started"
                    and opened.occurred_at <= event.occurred_at < ends_at
                ),
                None,
            )
            if question is not None:
                revisit_durations.append(
                    (question.occurred_at - opened.occurred_at).total_seconds()
                )

    return {
        "starts_at": starts_at,
        "ends_at": ends_at,
        "weekly_active_learners": len(active),
        "grounded_loop_completers": len(completers),
        "grounded_loop_completion_rate": (
            len(completers) / len(active) if active else 0.0
        ),
        "intent_to_grounded_grade_seconds": _percentiles(intent_durations),
        "revisit_open_to_question_seconds": _percentiles(revisit_durations),
    }
