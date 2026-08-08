"""Owner-scoped projections for the cross-workspace calendar."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from refineq.calendar.service import CalendarRangeError, CalendarService
from refineq.storage.json_store import AtomicJsonStore
from refineq.storage.learning import LearningRepository
from refineq.storage.workspaces import WorkspaceRepository


def _create_workspace(
    workspaces: WorkspaceRepository,
    learning: LearningRepository,
    *,
    owner_id: str,
    workspace_id: str,
    title: str,
    planned_at: datetime | None,
    archived: bool = False,
) -> None:
    workspaces.create(
        owner_id,
        workspace_id,
        title=title,
        subject="subject",
        goal=f"Learn {title}",
        topics=["Core topic"],
        keywords=[title],
        routing_summary=f"Route to {title}",
        now=datetime(2026, 7, 1, tzinfo=UTC),
    )
    if archived:
        workspaces.update(owner_id, workspace_id, archived=True)
    if planned_at is None:
        return

    def seed(data: dict) -> dict:
        data["progress"] = {
            "seeded": True,
            "topics": {"topic-core": f"{title} topic"},
            "plan": {
                "id": f"plan-{workspace_id}",
                "goal": f"Learn {title}",
                "exam_at": (planned_at + timedelta(days=30)).isoformat(),
                "daily_minutes": 30,
                "sessions": [
                    {
                        "id": f"session-{workspace_id}",
                        "topic_id": "topic-core",
                        "planned_at": planned_at.isoformat(),
                        "minutes": 30,
                        "activity": "practice",
                        "status": "planned",
                    }
                ],
            },
        }
        return data

    learning.mutate(owner_id, workspace_id, seed)


def _service(tmp_path: Path) -> tuple[CalendarService, WorkspaceRepository, LearningRepository]:
    store = AtomicJsonStore(tmp_path)
    workspaces = WorkspaceRepository(store)
    learning = LearningRepository(store)
    return CalendarService(workspaces=workspaces, learning=learning), workspaces, learning


def test_calendar_projects_only_owned_visible_tasks_in_half_open_range(
    tmp_path: Path,
) -> None:
    service, workspaces, learning = _service(tmp_path)
    starts_at = datetime(2026, 8, 1, tzinfo=UTC)
    ends_at = datetime(2026, 9, 1, tzinfo=UTC)
    _create_workspace(
        workspaces,
        learning,
        owner_id="alice",
        workspace_id="math",
        title="Mathematics",
        planned_at=starts_at + timedelta(days=8),
    )
    _create_workspace(
        workspaces,
        learning,
        owner_id="alice",
        workspace_id="english",
        title="English",
        planned_at=starts_at + timedelta(days=2),
        archived=True,
    )
    _create_workspace(
        workspaces,
        learning,
        owner_id="bob",
        workspace_id="private",
        title="Bob private",
        planned_at=starts_at + timedelta(days=1),
    )
    _create_workspace(
        workspaces,
        learning,
        owner_id="alice",
        workspace_id="empty",
        title="No plan",
        planned_at=None,
    )
    _create_workspace(
        workspaces,
        learning,
        owner_id="alice",
        workspace_id="boundary",
        title="Boundary",
        planned_at=ends_at,
    )

    response = service.list_tasks("alice", starts_at=starts_at, ends_at=ends_at)

    assert response.starts_at == starts_at
    assert response.ends_at == ends_at
    assert [task.workspace_id for task in response.tasks] == ["math"]
    task = response.tasks[0]
    assert task.workspace_title == "Mathematics"
    assert task.topic_label == "Mathematics topic"
    assert task.id == "session-math"
    assert task.activity == "practice"
    assert task.status == "planned"


def test_calendar_can_include_archived_spaces_and_sorts_stably(tmp_path: Path) -> None:
    service, workspaces, learning = _service(tmp_path)
    starts_at = datetime(2026, 8, 1, tzinfo=UTC)
    for workspace_id, title, offset, archived in (
        ("later", "Later", 8, False),
        ("archived", "Archived", 2, True),
        ("same-b", "Zulu", 4, False),
        ("same-a", "Alpha", 4, False),
    ):
        _create_workspace(
            workspaces,
            learning,
            owner_id="alice",
            workspace_id=workspace_id,
            title=title,
            planned_at=starts_at + timedelta(days=offset),
            archived=archived,
        )

    response = service.list_tasks(
        "alice",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(days=31),
        include_archived=True,
    )

    assert [task.workspace_id for task in response.tasks] == [
        "archived",
        "same-a",
        "same-b",
        "later",
    ]
    assert response.tasks[0].workspace_archived is True


def test_calendar_projects_the_name_from_canonical_structured_topics(tmp_path: Path) -> None:
    service, workspaces, learning = _service(tmp_path)
    starts_at = datetime(2026, 8, 1, tzinfo=UTC)
    _create_workspace(
        workspaces,
        learning,
        owner_id="alice",
        workspace_id="calculus",
        title="Calculus",
        planned_at=starts_at + timedelta(days=2),
    )

    def use_canonical_topic(data: dict) -> dict:
        data["progress"]["topics"]["topic-core"] = {
            "id": "topic-core",
            "name": "Limits and continuity",
            "knowledge_type": "concept",
        }
        return data

    learning.mutate("alice", "calculus", use_canonical_topic)

    response = service.list_tasks(
        "alice",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(days=31),
    )

    assert response.tasks[0].topic_label == "Limits and continuity"


@pytest.mark.parametrize(
    ("starts_at", "ends_at"),
    [
        (datetime(2026, 8, 1), datetime(2026, 8, 2, tzinfo=UTC)),
        (datetime(2026, 8, 2, tzinfo=UTC), datetime(2026, 8, 1, tzinfo=UTC)),
        (datetime(2026, 8, 1, tzinfo=UTC), datetime(2027, 8, 7, tzinfo=UTC)),
    ],
)
def test_calendar_rejects_invalid_or_unbounded_ranges(
    tmp_path: Path,
    starts_at: datetime,
    ends_at: datetime,
) -> None:
    service, _, _ = _service(tmp_path)

    with pytest.raises(CalendarRangeError):
        service.list_tasks("alice", starts_at=starts_at, ends_at=ends_at)
