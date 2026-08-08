"""Deterministic extraction of common study constraints from learner intent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

_WORD_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_CHINESE_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
_NUMBER = (
    r"\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"[零一二两三四五六七八九十]{1,3}"
)
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_ENGLISH_MONTH = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?"
)


@dataclass(frozen=True, slots=True)
class IntentConstraints:
    exam_at: datetime | None = None
    daily_minutes: int | None = None


def _number(value: str) -> int:
    normalized = value.casefold()
    if normalized.isdigit():
        return int(normalized)
    if normalized in _WORD_NUMBERS:
        return _WORD_NUMBERS[normalized]
    if normalized == "十":
        return 10
    if "十" in normalized:
        left, right = normalized.split("十", 1)
        tens = _CHINESE_DIGITS.get(left, 1) if left else 1
        units = _CHINESE_DIGITS.get(right, 0) if right else 0
        return tens * 10 + units
    if len(normalized) == 1 and normalized in _CHINESE_DIGITS:
        return _CHINESE_DIGITS[normalized]
    raise ValueError(f"unsupported number: {value}")


def _relative_exam(intent: str, now: datetime) -> datetime | None:
    english = re.search(
        rf"\b(?:in|within)\s+(?P<count>{_NUMBER})\s*(?P<unit>days?|weeks?|months?)\b",
        intent,
        flags=re.IGNORECASE,
    )
    if english:
        count = _number(english.group("count"))
        unit = english.group("unit").casefold()
        days = count * (7 if unit.startswith("week") else 30 if unit.startswith("month") else 1)
        return now + timedelta(days=days)

    chinese = re.search(rf"(?P<count>{_NUMBER})\s*(?P<unit>天|日|周|星期|个月)(?:后|内)", intent)
    if chinese:
        count = _number(chinese.group("count"))
        unit = chinese.group("unit")
        days = count * (7 if unit in {"周", "星期"} else 30 if unit == "个月" else 1)
        return now + timedelta(days=days)
    return None


def _exam_date(
    *,
    month: int,
    day: int,
    now: datetime,
    year: int | None = None,
) -> datetime | None:
    years = [year] if year is not None else list(range(now.year, now.year + 8))
    for candidate_year in years:
        if candidate_year is None:
            continue
        try:
            candidate = datetime(
                candidate_year,
                month,
                day,
                23,
                59,
                59,
                tzinfo=now.tzinfo,
            )
        except ValueError:
            continue
        if candidate > now:
            return candidate
        if year is not None:
            return None
    return None


def _absolute_exam(intent: str, now: datetime) -> datetime | None:
    chinese = re.search(
        rf"(?:(?P<year>\d{{4}})\s*年\s*)?"
        rf"(?P<month>{_NUMBER})\s*月\s*(?P<day>{_NUMBER})\s*(?:日|号)",
        intent,
        flags=re.IGNORECASE,
    )
    if chinese:
        return _exam_date(
            month=_number(chinese.group("month")),
            day=_number(chinese.group("day")),
            now=now,
            year=int(chinese.group("year")) if chinese.group("year") else None,
        )

    slash = re.search(
        r"(?<![\d/])(?P<month>\d{1,2})\s*/\s*(?P<day>\d{1,2})"
        r"(?:\s*/\s*(?P<year>\d{4}))?(?![\d/])",
        intent,
    )
    if slash:
        return _exam_date(
            month=int(slash.group("month")),
            day=int(slash.group("day")),
            now=now,
            year=int(slash.group("year")) if slash.group("year") else None,
        )

    english = re.search(
        rf"\b(?P<month>{_ENGLISH_MONTH})\s+"
        r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"
        r"(?:\s*,?\s*(?P<year>\d{4}))?\b",
        intent,
        flags=re.IGNORECASE,
    )
    if english:
        return _exam_date(
            month=_MONTHS[english.group("month")[:3].casefold()],
            day=int(english.group("day")),
            now=now,
            year=int(english.group("year")) if english.group("year") else None,
        )
    return None


def _daily_minutes(intent: str) -> int | None:
    patterns = (
        rf"(?P<count>{_NUMBER})\s*(?:minutes?|mins?)\s*(?:a\s+day|per\s+day|each\s+day|daily)",
        rf"(?:daily|each\s+day).{{0,24}}?(?P<count>{_NUMBER})\s*(?:minutes?|mins?)",
        rf"(?:每天|每日).{{0,12}}?(?P<count>{_NUMBER})\s*(?:分钟|分)",
        rf"(?P<count>{_NUMBER})\s*(?:分钟|分).{{0,8}}?(?:每天|每日)",
    )
    for pattern in patterns:
        matched = re.search(pattern, intent, flags=re.IGNORECASE)
        if matched:
            return _number(matched.group("count"))
    return None


def infer_intent_constraints(intent: str, *, now: datetime) -> IntentConstraints:
    """Extract unambiguous exam deadlines and per-day minute budgets."""

    return IntentConstraints(
        exam_at=_relative_exam(intent, now) or _absolute_exam(intent, now),
        daily_minutes=_daily_minutes(intent),
    )
