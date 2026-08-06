"""Behavioral tests for Bayesian knowledge tracing."""

from __future__ import annotations

import pytest

from refineq.learning.bkt import mastery_is_stable, update_bkt
from refineq.learning.models import BKTState


def test_correct_answer_increases_mastery_and_evidence() -> None:
    state = BKTState(p_mastery=0.2)

    updated = update_bkt(state, is_correct=True)

    assert updated.p_mastery > state.p_mastery
    assert updated.evidence_count == 1


def test_incorrect_answer_decreases_belief_before_learning_step() -> None:
    state = BKTState(p_mastery=0.8, p_learn=0.0)

    updated = update_bkt(state, is_correct=False)

    assert updated.p_mastery < state.p_mastery


def test_bkt_update_is_pure_and_probability_is_bounded() -> None:
    state = BKTState(p_mastery=0.999, p_learn=0.3)

    updated = update_bkt(state, is_correct=True)

    assert state.evidence_count == 0
    assert 0.0 <= updated.p_mastery <= 1.0


@pytest.mark.parametrize(
    ("state", "qualitative_gate", "expected"),
    [
        (BKTState(p_mastery=0.95, evidence_count=2), True, False),
        (BKTState(p_mastery=0.95, evidence_count=3), False, False),
        (BKTState(p_mastery=0.95, evidence_count=3), True, True),
    ],
)
def test_stable_mastery_requires_enough_evidence(
    state: BKTState,
    qualitative_gate: bool,
    expected: bool,
) -> None:
    assert mastery_is_stable(state, qualitative_gate=qualitative_gate) is expected
