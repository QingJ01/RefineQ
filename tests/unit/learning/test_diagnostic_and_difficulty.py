"""Tests for adaptive diagnosis and practice difficulty."""

from __future__ import annotations

import pytest

from refineq.learning.diagnostic import choose_next_candidate, should_stop
from refineq.learning.difficulty import update_difficulty
from refineq.learning.models import (
    AdaptiveDiagnosticSession,
    DiagnosticCandidate,
    DifficultyState,
)


def test_diagnostic_prefers_unseen_high_information_point() -> None:
    candidates = [
        DiagnosticCandidate(
            knowledge_point_id="already-strong",
            p_mastery=0.9,
            assessment_count=2,
        ),
        DiagnosticCandidate(
            knowledge_point_id="unseen-middle",
            p_mastery=0.5,
            assessment_count=0,
        ),
        DiagnosticCandidate(
            knowledge_point_id="unseen-extreme",
            p_mastery=0.05,
            assessment_count=0,
        ),
    ]

    selected = choose_next_candidate(candidates)

    assert selected is not None
    assert selected.knowledge_point_id == "unseen-middle"


@pytest.mark.parametrize(
    ("session", "expected"),
    [
        (AdaptiveDiagnosticSession(answer_count=7, confidence=1.0), False),
        (AdaptiveDiagnosticSession(answer_count=8, confidence=0.8), True),
        (AdaptiveDiagnosticSession(answer_count=10, confidence=0.5), False),
        (AdaptiveDiagnosticSession(answer_count=12, confidence=0.2), True),
    ],
)
def test_diagnostic_stopping_policy(
    session: AdaptiveDiagnosticSession,
    expected: bool,
) -> None:
    assert should_stop(session) is expected


def test_two_distinct_correct_answers_raise_difficulty() -> None:
    state = DifficultyState(level=2)

    state = update_difficulty(state, is_correct=True, question_id="q1")
    state = update_difficulty(state, is_correct=True, question_id="q2")

    assert state.level == 3
    assert state.recent_correct_question_ids == []


def test_retrying_same_question_does_not_raise_difficulty() -> None:
    state = DifficultyState(level=2)

    state = update_difficulty(state, is_correct=True, question_id="q1")
    state = update_difficulty(state, is_correct=True, question_id="q1")

    assert state.level == 2


def test_two_wrong_answers_lower_difficulty_without_falling_below_one() -> None:
    state = DifficultyState(level=1)

    state = update_difficulty(state, is_correct=False, question_id="q1")
    state = update_difficulty(state, is_correct=False, question_id="q2")

    assert state.level == 1
    assert state.consecutive_wrong == 0


def test_blank_question_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="question_id"):
        update_difficulty(DifficultyState(), is_correct=True, question_id="  ")
