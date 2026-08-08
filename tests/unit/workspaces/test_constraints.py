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


def test_extracts_english_absolute_exam_and_daily_minutes() -> None:
    constraints = infer_intent_constraints(
        "Computer Architecture midterm on October 25, 90 minutes a day",
        now=NOW,
    )

    assert constraints.exam_at == datetime(2026, 10, 25, 23, 59, 59, tzinfo=UTC)
    assert constraints.daily_minutes == 90


def test_ambiguous_intent_does_not_invent_constraints() -> None:
    constraints = infer_intent_constraints("Help me get better at calculus", now=NOW)

    assert constraints.exam_at is None
    assert constraints.daily_minutes is None
