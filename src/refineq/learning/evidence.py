"""Idempotent evidence and recommendation construction."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from hashlib import sha256
from typing import Any

from refineq.learning.models import LearningEvidence, LearningRecommendation


def stable_id(namespace: str, *parts: str) -> str:
    """Return a readable deterministic ID for an immutable business identity."""

    normalized = "\x1f".join(part.strip() for part in parts)
    digest = sha256(f"{namespace}\x1e{normalized}".encode()).hexdigest()[:20]
    return f"{namespace}_{digest}"


def create_evidence(
    *,
    kind: str,
    source_id: str,
    summary: str,
    observed_at: datetime,
    details: dict[str, Any] | None = None,
) -> LearningEvidence:
    """Construct an idempotent evidence event from its external source key."""

    return LearningEvidence(
        id=stable_id("evidence", kind, source_id),
        kind=kind,
        source_id=source_id.strip(),
        summary=summary.strip(),
        observed_at=observed_at,
        details=details or {},
    )


def make_recommendation(
    *,
    action: str,
    rationale: str,
    evidence: Iterable[LearningEvidence],
) -> LearningRecommendation:
    """Create a recommendation only when its supporting evidence is explicit."""

    evidence_ids = list(dict.fromkeys(item.id for item in evidence))
    if not evidence_ids:
        raise ValueError("recommendation requires at least one evidence item")
    return LearningRecommendation(
        id=stable_id("recommendation", action, *sorted(evidence_ids)),
        action=action.strip(),
        rationale=rationale.strip(),
        evidence_ids=evidence_ids,
    )
