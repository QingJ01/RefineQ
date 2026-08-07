"""Prompt context assembled from trusted learning state and untrusted sources."""

from __future__ import annotations

import json
from typing import Any

from refineq.knowledge.index import SearchResult


def build_agent_context(
    *,
    goal: str,
    plan: dict[str, Any] | None,
    mastery: dict[str, float],
    sources: list[SearchResult],
    session_context: dict[str, str] | None = None,
) -> str:
    """Build a grounded system prompt with an explicit trust boundary."""

    weak_points = sorted(mastery.items(), key=lambda item: (item[1], item[0]))[:5]
    payload = {
        "goal": goal,
        "study_plan": plan,
        "weakest_knowledge_points": [
            {"topic": topic, "mastery": round(score, 3)} for topic, score in weak_points
        ],
        "retrieved_materials": [
            {
                "citation_id": source.citation_id,
                "filename": source.filename,
                "text": source.text[:4_000],
            }
            for source in sources
        ],
        "current_session": session_context,
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    serialized = serialized.replace("<", "\\u003c").replace(">", "\\u003e")
    return f"<untrusted_learning_context>\n{serialized}\n</untrusted_learning_context>"
