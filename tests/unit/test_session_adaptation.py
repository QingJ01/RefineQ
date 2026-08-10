from refineq.learning.session_adaptation import (
    decide_next_session_action,
    estimated_task_minutes,
    summary_reserve_minutes,
)


def test_short_session_reserves_time_for_summary() -> None:
    decision = decide_next_session_action(
        current_topic_id="limits",
        current_mastery=0.4,
        difficulty_level=3,
        topic_order=["limits", "derivatives"],
        mastery_by_topic={"limits": 0.4, "derivatives": 0.0},
        remaining_minutes=9,
        reserve_minutes=4,
    )

    assert decision.action == "summary"
    assert decision.reason == "time_low"


def test_low_mastery_keeps_current_topic_when_time_allows() -> None:
    decision = decide_next_session_action(
        current_topic_id="limits",
        current_mastery=0.6,
        difficulty_level=2,
        topic_order=["limits", "derivatives"],
        mastery_by_topic={"limits": 0.6, "derivatives": 0.0},
        remaining_minutes=30,
        reserve_minutes=6,
    )

    assert decision.action == "continue_topic"
    assert decision.topic_id == "limits"


def test_mastered_topic_advances_to_next_unmastered_topic() -> None:
    decision = decide_next_session_action(
        current_topic_id="limits",
        current_mastery=0.82,
        difficulty_level=4,
        topic_order=["limits", "derivatives", "integrals"],
        mastery_by_topic={"limits": 0.82, "derivatives": 0.8, "integrals": 0.2},
        remaining_minutes=35,
        reserve_minutes=6,
    )

    assert decision.action == "next_topic"
    assert decision.topic_id == "integrals"


def test_duration_and_reserve_tables_are_bounded() -> None:
    assert [estimated_task_minutes(level) for level in range(1, 6)] == [3, 4, 6, 9, 12]
    assert [summary_reserve_minutes(minutes) for minutes in (20, 45, 75, 120)] == [4, 6, 8, 10]
