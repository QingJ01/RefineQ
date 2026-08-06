"""Pure Bayesian knowledge-tracing updates."""

from __future__ import annotations

from refineq.learning.models import BKTState

DEFAULT_BKT = BKTState()


def update_bkt(state: BKTState, *, is_correct: bool) -> BKTState:
    """Return a posterior state without mutating the supplied state."""

    prior = state.p_mastery
    if is_correct:
        numerator = prior * (1.0 - state.p_slip)
        denominator = numerator + (1.0 - prior) * state.p_guess
    else:
        numerator = prior * state.p_slip
        denominator = numerator + (1.0 - prior) * (1.0 - state.p_guess)

    posterior = numerator / denominator if denominator > 0 else prior
    learned = posterior + (1.0 - posterior) * state.p_learn
    return state.model_copy(
        update={
            "p_mastery": min(1.0, max(0.0, learned)),
            "evidence_count": state.evidence_count + 1,
        }
    )


def mastery_is_stable(
    state: BKTState,
    *,
    qualitative_gate: bool = True,
    threshold: float = 0.85,
    minimum_evidence: int = 3,
) -> bool:
    """Require probability, repeated evidence, and qualitative understanding."""

    return (
        qualitative_gate
        and state.evidence_count >= minimum_evidence
        and state.p_mastery >= threshold
    )
