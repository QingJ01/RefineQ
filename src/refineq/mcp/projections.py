"""Bounded read models for MCP; these functions never create or mutate state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from refineq.knowledge.index import KnowledgeIndex
from refineq.storage.learning import LearningRepository
from refineq.storage.workspaces import WorkspaceRepository


def learning_context_projection(
    *,
    owner_id: str,
    workspace_id: str,
    workspaces: WorkspaceRepository,
    learning: LearningRepository,
    knowledge: KnowledgeIndex,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    workspace = workspaces.get(owner_id, workspace_id)
    record = learning.get(owner_id, workspace_id)
    progress = record.data["progress"]
    topics = []
    topic_ids = list(progress.get("topic_order") or progress["topics"])
    for topic_id in topic_ids[:8]:
        topic = progress["topics"][topic_id]
        mastery = float(progress["bkt_states"][topic_id].get("p_mastery", 0.0))
        topics.append(
            {
                "id": topic_id,
                "name": str(topic.get("name") or topic_id),
                "mastery": round(mastery, 4),
            }
        )
    sessions = []
    for session in (progress.get("plan") or {}).get("sessions", []):
        planned_at = datetime.fromisoformat(str(session["planned_at"]))
        if planned_at.tzinfo is None:
            planned_at = planned_at.replace(tzinfo=UTC)
        if planned_at.astimezone(UTC).date() == observed_at.date():
            sessions.append(
                {
                    "id": session["id"],
                    "topic_id": session["topic_id"],
                    "activity": session.get("activity", "practice"),
                    "minutes": int(session["minutes"]),
                    "status": session.get("status", "planned"),
                    "planned_at": planned_at.astimezone(UTC).isoformat(),
                }
            )
        if len(sessions) >= 8:
            break
    pending = progress.get("pending_question")
    pending_public = None
    if pending is not None:
        pending_public = {
            "id": pending["id"],
            "topic_id": pending["topic_id"],
            "prompt": pending["prompt"],
            "difficulty": int(pending.get("difficulty_level", 2)),
            "citations": list(pending.get("citations") or [])[:8],
            "grounding": pending.get("grounding", "general"),
        }
    material_records = knowledge.list_materials(
        owner_id=owner_id,
        project_id=workspace_id,
        status="indexed",
    )
    evidence = []
    for item in list(progress.get("evidence") or [])[-5:]:
        evidence.append(
            {
                "id": item.get("id"),
                "kind": item.get("kind"),
                "summary": str(item.get("summary") or "")[:300],
                "observed_at": item.get("observed_at"),
            }
        )
    return {
        "workspace": {
            "id": workspace.id,
            "title": workspace.title,
            "subject": workspace.subject,
            "goal": workspace.goal,
            "exam_at": progress.get("exam_at"),
            "daily_minutes": int(progress.get("daily_minutes", 0)),
        },
        "topics": topics,
        "today_sessions": sessions,
        "pending_question": pending_public,
        "materials": {
            "indexed_count": len(material_records),
            "items": [
                {"id": item.id, "title": item.title, "status": item.status}
                for item in material_records[:8]
            ],
        },
        "latest_evidence": evidence,
        "next_action": (
            {
                "tool": "refineq_submit_answer",
                "reason": "A practice task is awaiting an answer.",
            }
            if pending_public is not None
            else {
                "tool": "refineq_get_practice_task",
                "reason": "The sandbox is ready for a source-grounded task.",
            }
        ),
        "state_version": record.version,
        "truncated": (
            len(topic_ids) > 8
            or len((progress.get("plan") or {}).get("sessions", [])) > len(sessions)
            or len(material_records) > 8
            or len(progress.get("evidence") or []) > 5
        ),
    }


def material_search_projection(
    *,
    owner_id: str,
    workspace_id: str,
    query: str,
    limit: int,
    knowledge: KnowledgeIndex,
) -> dict[str, Any]:
    results, retrieval_mode = knowledge.search_with_mode(
        owner_id=owner_id,
        project_id=workspace_id,
        query=query,
        limit=min(limit, 8),
    )
    projected: list[dict[str, Any]] = []
    # Leave room for the run token, query, schema envelope, and JSON punctuation.
    byte_budget = 6 * 1024
    used = 0
    truncated = False
    for item in results:
        excerpt = item.text[:400]
        candidate = {
            "citation_id": item.citation_id,
            "material_id": item.material_id,
            "filename": item.filename,
            "excerpt": excerpt,
            "score": round(item.score, 6),
        }
        size = len(str(candidate).encode("utf-8"))
        if used + size > byte_budget:
            truncated = True
            break
        used += size
        projected.append(candidate)
    return {
        "results": projected,
        "retrieval_mode": retrieval_mode,
        "truncated": truncated,
    }
