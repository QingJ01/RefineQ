"""Deterministic adaptive-diagnostic selection and stopping policies."""

from __future__ import annotations

from collections.abc import Iterable

from refineq.learning.models import AdaptiveDiagnosticSession, DiagnosticCandidate


def candidate_score(candidate: DiagnosticCandidate) -> float:
    """Score how useful a knowledge point would be to assess next."""

    information = 1.0 - 2.0 * abs(candidate.p_mastery - 0.5)
    unseen = 4.0 if candidate.assessment_count == 0 else 0.0
    return (
        unseen
        + max(0.0, information) * 2.0
        + candidate.recent_errors * 0.6
        + candidate.exam_weight * 0.5
        + candidate.prerequisite_gap * 0.5
        - min(candidate.assessment_count, 4) * 0.25
    )


def choose_next_candidate(
    candidates: Iterable[DiagnosticCandidate],
) -> DiagnosticCandidate | None:
    ranked = sorted(
        candidates,
        key=lambda candidate: (-candidate_score(candidate), candidate.knowledge_point_id),
    )
    return ranked[0] if ranked else None


def should_stop(session: AdaptiveDiagnosticSession) -> bool:
    if session.answer_count >= session.maximum_questions:
        return True
    if session.answer_count < session.minimum_questions:
        return False
    return session.confidence >= 0.75
