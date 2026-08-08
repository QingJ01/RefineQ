"""Tests for evidence-independent practice difficulty transitions."""

from __future__ import annotations

import pytest

from refineq.learning.difficulty import update_difficulty
from refineq.learning.models import DifficultyState


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


def test_retrying_the_same_wrong_question_does_not_lower_difficulty() -> None:
    state = DifficultyState(level=3)

    state = update_difficulty(state, is_correct=False, question_id="q1")
    state = update_difficulty(state, is_correct=False, question_id="q1")

    assert state.level == 3


@pytest.mark.parametrize(
    ("answers", "levels"),
    [
        ([True, False, True, False], [2, 2, 2, 2]),
        ([True, False, True, True], [2, 2, 2, 3]),
        ([False, True, False, False], [2, 2, 2, 1]),
    ],
)
def test_difficulty_requires_consecutive_independent_evidence(
    answers: list[bool],
    levels: list[int],
) -> None:
    state = DifficultyState(level=2)
    observed: list[int] = []

    for index, is_correct in enumerate(answers):
        state = update_difficulty(state, is_correct=is_correct, question_id=f"q{index}")
        observed.append(state.level)

    assert observed == levels


def test_blank_question_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="question_id"):
        update_difficulty(DifficultyState(), is_correct=True, question_id="  ")
