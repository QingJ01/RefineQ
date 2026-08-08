"""Backup archives are validated, portable, and restored without overwriting data."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from refineq.config import Settings
from refineq.database.engine import Database
from refineq.knowledge.index import KnowledgeIndex
from refineq.operations.admin import AdminOperations
from refineq.operations.backup import (
    BackupError,
    BackupValidationError,
    RestoreConflictError,
    create_backup,
    create_managed_backup,
    list_managed_backups,
    restore_backup,
    validate_managed_backup,
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


def test_managed_backups_use_opaque_ids_and_support_full_restore_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backup_module = __import__("refineq.operations.backup", fromlist=["tempfile"])
    original_temporary_directory = backup_module.tempfile.TemporaryDirectory
    temporary_parents: list[Path | None] = []

    def tracked_temporary_directory(*args, **kwargs):
        parent = kwargs.get("dir")
        temporary_parents.append(Path(parent) if parent is not None else None)
        return original_temporary_directory(*args, **kwargs)

    monkeypatch.setattr(
        backup_module.tempfile,
        "TemporaryDirectory",
        tracked_temporary_directory,
    )
    source = tmp_path / "runtime"
    backup_root = tmp_path / "managed-backups"
    _seed_runtime(source)
    deeply_nested = (
        source
        / "users"
        / ("user_" + "a" * 32)
        / "workspaces"
        / ("workspace_" + "b" * 32)
        / "materials"
        / ("material_" + "c" * 32)
    )
    deeply_nested.parent.mkdir(parents=True)
    deeply_nested.write_text("long portable path", encoding="utf-8")

    created = create_managed_backup(source, backup_root)
    listed = list_managed_backups(backup_root)
    temporary_parents.clear()
    validated = validate_managed_backup(backup_root, created.id)

    assert created.id.startswith("backup_")
    assert "/" not in created.id and "\\" not in created.id
    assert listed == [created]
    assert validated.id == created.id
    assert validated.file_count == created.file_count
    assert validated.total_bytes == created.total_bytes
    assert temporary_parents[0] is None


@pytest.mark.parametrize("backup_id", ["../outside", "..\\outside", "backup_invalid.zip"])
def test_managed_backup_validation_rejects_paths_and_unissued_ids(
    tmp_path: Path,
    backup_id: str,
) -> None:
    backup_root = tmp_path / "managed-backups"
    backup_root.mkdir()

    with pytest.raises(BackupValidationError):
        validate_managed_backup(backup_root, backup_id)


def test_managed_backup_is_removed_when_audit_write_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(data_root=tmp_path / "runtime", _env_file=None)
    settings.data_root.mkdir(parents=True)
    (settings.data_root / "safe.txt").write_text("safe", encoding="utf-8")
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'admin.sqlite3').as_posix()}")
    database.initialize()
    operations = AdminOperations(database, settings)

    def fail_audit(**_kwargs: object) -> None:
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(operations, "audit", fail_audit)

    with pytest.raises(BackupError):
        operations.create_backup(actor_id="admin")

    assert operations.list_backups() == []
