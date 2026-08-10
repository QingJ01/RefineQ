from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SessionAction = Literal["continue_topic", "next_topic", "summary"]
SessionDecisionReason = Literal[
    "time_low",
    "mastery_low",
    "mastery_reached",
    "no_next_topic",
]

MASTERY_TARGET = 0.75


def summary_reserve_minutes(total_minutes: int) -> int:
    if total_minutes <= 25:
        desired = 4
    elif total_minutes <= 60:
        desired = 6
    elif total_minutes <= 90:
        desired = 8
    else:
        desired = 10
    return min(desired, max(1, total_minutes - 3))


def estimated_task_minutes(difficulty_level: int) -> int:
    return {1: 3, 2: 4, 3: 6, 4: 9, 5: 12}.get(difficulty_level, 6)


@dataclass(frozen=True)
class AdaptiveSessionDecision:
    action: SessionAction
    reason: SessionDecisionReason
    topic_id: str | None
    estimated_minutes: int
    remaining_minutes: int | None
    summary_reserve_minutes: int
    target_mastery: float = MASTERY_TARGET


def decide_next_session_action(
    *,
    current_topic_id: str,
    current_mastery: float,
    difficulty_level: int,
    topic_order: list[str],
    mastery_by_topic: dict[str, float],
    remaining_minutes: int | None,
    reserve_minutes: int,
) -> AdaptiveSessionDecision:
    estimate = estimated_task_minutes(difficulty_level)
    if remaining_minutes is not None and remaining_minutes < estimate + reserve_minutes:
        return AdaptiveSessionDecision(
            action="summary",
            reason="time_low",
            topic_id=current_topic_id,
            estimated_minutes=estimate,
            remaining_minutes=remaining_minutes,
            summary_reserve_minutes=reserve_minutes,
        )

    if current_mastery < MASTERY_TARGET:
        return AdaptiveSessionDecision(
            action="continue_topic",
            reason="mastery_low",
            topic_id=current_topic_id,
            estimated_minutes=estimate,
            remaining_minutes=remaining_minutes,
            summary_reserve_minutes=reserve_minutes,
        )

    try:
        current_index = topic_order.index(current_topic_id)
    except ValueError:
        current_index = -1
    next_topic_id = next(
        (
            topic_id
            for topic_id in topic_order[current_index + 1 :]
            if mastery_by_topic.get(topic_id, 0.0) < MASTERY_TARGET
        ),
        None,
    )
    if next_topic_id is not None:
        return AdaptiveSessionDecision(
            action="next_topic",
            reason="mastery_reached",
            topic_id=next_topic_id,
            estimated_minutes=estimate,
            remaining_minutes=remaining_minutes,
            summary_reserve_minutes=reserve_minutes,
        )
    return AdaptiveSessionDecision(
        action="summary",
        reason="no_next_topic",
        topic_id=current_topic_id,
        estimated_minutes=estimate,
        remaining_minutes=remaining_minutes,
        summary_reserve_minutes=reserve_minutes,
    )
