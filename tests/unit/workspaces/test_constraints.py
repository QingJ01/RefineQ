"""Natural-language study constraint extraction contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from refineq.workspaces.constraints import infer_intent_constraints

NOW = datetime(2026, 8, 6, 8, 0, tzinfo=UTC)


def test_extracts_chinese_relative_exam_and_daily_minutes() -> None:
    constraints = infer_intent_constraints("两周内考试，每天学习二十分钟", now=NOW)

    assert constraints.exam_at == NOW + timedelta(days=14)
    assert constraints.daily_minutes == 20


def test_extracts_chinese_absolute_exam_and_daily_minutes() -> None:
    constraints = infer_intent_constraints(
        "10 月 25 日考计算机组成原理期中，每天能学 90 分钟",
        now=NOW,
    )

    assert constraints.exam_at == datetime(2026, 10, 25, 23, 59, 59, tzinfo=UTC)
    assert constraints.daily_minutes == 90


def test_extracts_chinese_hours_and_preferred_start_time() -> None:
    constraints = infer_intent_constraints(
        "我8月15号考试考计算机，每天晚上六点开始学习两个小时",
        now=NOW,
    )

    assert constraints.exam_at == datetime(2026, 8, 15, 23, 59, 59, tzinfo=UTC)
    assert constraints.daily_minutes == 120
    assert constraints.preferred_hour == 18


def test_extracts_english_absolute_exam_and_daily_minutes() -> None:
    constraints = infer_intent_constraints(
        "Computer Architecture midterm on October 25, 90 minutes a day",
        now=NOW,
    )

    assert constraints.exam_at == datetime(2026, 10, 25, 23, 59, 59, tzinfo=UTC)
    assert constraints.daily_minutes == 90


def test_extracts_slash_absolute_exam_date() -> None:
    constraints = infer_intent_constraints("Computer Architecture exam on 10/25", now=NOW)

    assert constraints.exam_at == datetime(2026, 10, 25, 23, 59, 59, tzinfo=UTC)


def test_explicit_relative_exam_constraint_wins_over_calendar_reference() -> None:
    constraints = infer_intent_constraints(
        "复习 10 月 25 日的真题，30 天后考试",
        now=NOW,
    )

    assert constraints.exam_at == NOW + timedelta(days=30)


def test_ambiguous_intent_does_not_invent_constraints() -> None:
    constraints = infer_intent_constraints("Help me get better at calculus", now=NOW)

    assert constraints.exam_at is None
    assert constraints.daily_minutes is None
    assert constraints.plan_requested is False


def test_explicit_plan_request_is_detected_without_time_constraints() -> None:
    constraints = infer_intent_constraints("帮我制定一个计算机学习计划", now=NOW)

    assert constraints.exam_at is None
    assert constraints.daily_minutes is None
    assert constraints.plan_requested is True


def test_absolute_exam_date_already_passed_rolls_into_next_year() -> None:
    constraints = infer_intent_constraints("3月14日考试", now=NOW)

    assert constraints.exam_at == datetime(2027, 3, 14, 23, 59, 59, tzinfo=UTC)


def test_extracts_slash_and_english_absolute_dates() -> None:
    assert infer_intent_constraints("exam on 12/20", now=NOW).exam_at == datetime(
        2026, 12, 20, 23, 59, 59, tzinfo=UTC
    )
    assert infer_intent_constraints("final exam Oct 25", now=NOW).exam_at == datetime(
        2026, 10, 25, 23, 59, 59, tzinfo=UTC
    )


def test_ambiguous_calendar_windows_do_not_invent_exact_deadlines() -> None:
    assert infer_intent_constraints("下周考数据库系统", now=NOW).exam_at is None
    assert infer_intent_constraints("下个月考试", now=NOW).exam_at is None


def test_relative_deadline_wins_over_unrelated_numbers() -> None:
    constraints = infer_intent_constraints("30天后考试，每天60分钟", now=NOW)

    assert constraints.exam_at == NOW + timedelta(days=30)
    assert constraints.daily_minutes == 60


def test_invalid_calendar_dates_are_ignored() -> None:
    assert infer_intent_constraints("2月30日考试", now=NOW).exam_at is None
    assert infer_intent_constraints("13月1日考试", now=NOW).exam_at is None
