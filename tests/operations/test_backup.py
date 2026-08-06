"""Backup archives are validated, portable, and restored without overwriting data."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from refineq.knowledge.index import KnowledgeIndex
from refineq.operations.backup import (
    BackupValidationError,
    RestoreConflictError,
    create_backup,
    restore_backup,
)
from refineq.storage.json_store import AtomicJsonStore
from refineq.storage.projects import ProjectRepository


def _seed_runtime(root: Path) -> None:
    projects = ProjectRepository(AtomicJsonStore(root))
    projects.create("user_demo", "project_demo", name="Calculus")
    KnowledgeIndex(root).add_document(
        owner_id="user_demo",
        project_id="project_demo",
        material_id="material_demo",
        filename="notes.txt",
        text="A derivative is a local rate of change.",
    )


def test_backup_round_trip_preserves_json_and_sqlite(tmp_path: Path) -> None:
    source = tmp_path / "source"
    archive = tmp_path / "backups" / "snapshot.zip"
    restored = tmp_path / "restored"
    _seed_runtime(source)

    result = create_backup(source, archive)
    restored_result = restore_backup(archive, restored)

    assert result.archive == archive.resolve()
    assert result.file_count >= 2
    assert restored_result.destination == restored.resolve()
    project = ProjectRepository(AtomicJsonStore(restored)).get("user_demo", "project_demo")
    assert project.data["name"] == "Calculus"
    matches = KnowledgeIndex(restored).search(
        owner_id="user_demo",
        project_id="project_demo",
        query="derivative",
    )
    assert matches[0].material_id == "material_demo"


def test_restore_refuses_non_empty_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    archive = tmp_path / "snapshot.zip"
    destination = tmp_path / "destination"
    _seed_runtime(source)
    create_backup(source, archive)
    destination.mkdir()
    (destination / "keep.txt").write_text("important", encoding="utf-8")

    with pytest.raises(RestoreConflictError):
        restore_backup(archive, destination)

    assert (destination / "keep.txt").read_text(encoding="utf-8") == "important"


def test_restore_rejects_tampered_payload_before_creating_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    archive = tmp_path / "snapshot.zip"
    tampered = tmp_path / "tampered.zip"
    destination = tmp_path / "destination"
    _seed_runtime(source)
    create_backup(source, archive)

    with zipfile.ZipFile(archive) as original, zipfile.ZipFile(tampered, "w") as modified:
        for name in original.namelist():
            payload = original.read(name)
            if name.endswith("project_demo.json"):
                document = json.loads(payload)
                document["data"]["name"] = "Tampered"
                payload = json.dumps(document).encode()
            modified.writestr(name, payload)

    with pytest.raises(BackupValidationError):
        restore_backup(tampered, destination)

    assert not destination.exists()


def test_restore_rejects_archive_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("manifest.json", '{"format": "refineq-backup", "version": 1, "files": []}')
        bundle.writestr("data/../../escape.txt", "unsafe")

    with pytest.raises(BackupValidationError):
        restore_backup(archive, tmp_path / "destination")

    assert not (tmp_path / "escape.txt").exists()
