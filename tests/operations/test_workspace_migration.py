"""Tests for the backup-first legacy project migration."""

from __future__ import annotations

import zipfile
from pathlib import Path

from refineq.operations.workspace_migration import migrate_projects_to_workspaces
from refineq.storage.json_store import AtomicJsonStore


def test_migration_creates_backup_and_rewrites_legacy_records(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    archive = tmp_path / "backups" / "before-workspaces.zip"
    store = AtomicJsonStore(data_root)
    owner_id = "learner-1"
    legacy_id = "calculus-final"
    store.create(
        owner_id,
        "projects",
        legacy_id,
        {
            "id": legacy_id,
            "name": "Calculus final",
            "created_at": "2026-08-01T08:00:00+00:00",
        },
    )
    store.create(
        owner_id,
        "learning",
        legacy_id,
        {
            "project_id": legacy_id,
            "attempts": {},
            "progress": {
                "seeded": True,
                "goal": "Pass the calculus final",
                "topics": {
                    "limits": {"id": "limits", "name": "Limits"},
                    "derivatives": {"id": "derivatives", "name": "Derivatives"},
                },
            },
        },
    )
    store.create(
        owner_id,
        "sessions",
        "session-1",
        {"project_id": legacy_id, "stage": "practice"},
    )

    result = migrate_projects_to_workspaces(data_root, archive)

    assert result.migrated_count == 1
    assert result.backup is not None
    assert result.backup.archive == archive.resolve()
    assert archive.is_file()
    with zipfile.ZipFile(archive) as backup:
        assert f"data/users/{owner_id}/projects/{legacy_id}.json" in backup.namelist()

    workspace = store.read(owner_id, "workspaces", legacy_id).data
    assert workspace["title"] == "Calculus final"
    assert workspace["goal"] == "Pass the calculus final"
    assert set(workspace["topics"]) == {"Limits", "Derivatives"}
    assert not (data_root / "users" / owner_id / "projects" / f"{legacy_id}.json").exists()

    learning = store.read(owner_id, "learning", legacy_id).data
    assert learning["workspace_id"] == legacy_id
    assert "project_id" not in learning
    session = store.read(owner_id, "sessions", "session-1").data
    assert session["workspace_id"] == legacy_id
    assert "project_id" not in session

    replay = migrate_projects_to_workspaces(data_root, tmp_path / "unused.zip")
    assert replay.migrated_count == 0
    assert replay.backup is None
    assert not (tmp_path / "unused.zip").exists()


def test_migration_does_not_modify_data_when_workspace_conflicts(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    archive = tmp_path / "conflict-backup.zip"
    store = AtomicJsonStore(data_root)
    store.create(
        "learner-1",
        "projects",
        "shared-id",
        {"id": "shared-id", "name": "Legacy title", "created_at": "2026-08-01T08:00:00+00:00"},
    )
    store.create(
        "learner-1",
        "workspaces",
        "shared-id",
        {
            "id": "shared-id",
            "title": "Different title",
            "subject": "general",
            "goal": "Different goal",
            "topics": ["Different topic"],
            "keywords": ["different"],
            "routing_summary": "existing",
            "created_at": "2026-08-01T08:00:00+00:00",
            "last_active_at": "2026-08-01T08:00:00+00:00",
        },
    )

    try:
        migrate_projects_to_workspaces(data_root, archive)
    except RuntimeError as error:
        assert "conflict" in str(error).casefold()
    else:
        raise AssertionError("A conflicting workspace must stop migration")

    assert not archive.exists()
    assert (data_root / "users" / "learner-1" / "projects" / "shared-id.json").exists()
