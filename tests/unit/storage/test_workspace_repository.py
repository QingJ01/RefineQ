"""Owner-scoped persistence tests for implicit learning workspaces."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from refineq.storage.json_store import AtomicJsonStore
from refineq.storage.workspaces import WorkspaceRepository


def test_workspaces_are_listed_by_latest_activity(tmp_path: Path) -> None:
    repository = WorkspaceRepository(AtomicJsonStore(tmp_path))
    earlier = datetime(2026, 8, 5, 8, 0, tzinfo=UTC)
    later = earlier + timedelta(hours=2)

    repository.create(
        "owner",
        "math",
        title="高等数学",
        subject="mathematics",
        goal="准备高数期末",
        topics=["极限"],
        keywords=["高数", "极限"],
        routing_summary="高等数学学习",
        now=earlier,
    )
    repository.create(
        "owner",
        "english",
        title="英语四级",
        subject="language",
        goal="通过英语四级",
        topics=["词汇"],
        keywords=["英语", "四级"],
        routing_summary="英语学习",
        now=later,
    )

    assert [item.id for item in repository.list("owner")] == ["english", "math"]


def test_touch_updates_activity_without_changing_the_workspace_identity(
    tmp_path: Path,
) -> None:
    repository = WorkspaceRepository(AtomicJsonStore(tmp_path))
    created_at = datetime(2026, 8, 5, 8, 0, tzinfo=UTC)
    touched_at = created_at + timedelta(days=1)
    repository.create(
        "owner",
        "math",
        title="高等数学",
        subject="mathematics",
        goal="准备高数期末",
        topics=["极限"],
        keywords=["高数", "极限"],
        routing_summary="高等数学学习",
        now=created_at,
    )

    touched = repository.touch("owner", "math", now=touched_at)

    assert touched.id == "math"
    assert touched.created_at == created_at
    assert touched.last_active_at == touched_at


def test_workspace_listing_is_owner_scoped(tmp_path: Path) -> None:
    repository = WorkspaceRepository(AtomicJsonStore(tmp_path))
    now = datetime(2026, 8, 5, 8, 0, tzinfo=UTC)
    for owner in ("alice", "bob"):
        repository.create(
            owner,
            f"{owner}-space",
            title=owner,
            subject="general",
            goal=f"{owner} goal",
            topics=[owner],
            keywords=[owner],
            routing_summary="owner scope",
            now=now,
        )

    assert [item.id for item in repository.list("alice")] == ["alice-space"]

