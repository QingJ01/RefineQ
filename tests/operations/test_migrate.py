"""Runtime migration is backup-first, validated, and non-overwriting."""

from __future__ import annotations

from pathlib import Path

import pytest

from refineq.operations.backup import BackupValidationError
from refineq.operations.migrate import MigrationConflictError, migrate_data


def test_migrate_creates_verified_backup_before_installing_data(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    archive = tmp_path / "backups" / "before-migration.zip"
    record = source / "users" / "user_demo" / "projects" / "project_demo.json"
    record.parent.mkdir(parents=True)
    record.write_text(
        '{"schema_version": 1, "version": 1, "data": {"id": "project_demo"}}',
        encoding="utf-8",
    )

    result = migrate_data(source, destination, archive)

    assert result.backup.archive == archive.resolve()
    assert archive.is_file()
    assert (destination / record.relative_to(source)).read_bytes() == record.read_bytes()


def test_migrate_rejects_malformed_source_without_partial_destination(tmp_path: Path) -> None:
    source = tmp_path / "source"
    malformed = source / "users" / "user_demo" / "projects" / "bad.json"
    malformed.parent.mkdir(parents=True)
    malformed.write_text("not-json", encoding="utf-8")
    destination = tmp_path / "destination"
    archive = tmp_path / "backup.zip"

    with pytest.raises(BackupValidationError):
        migrate_data(source, destination, archive)

    assert not archive.exists()
    assert not destination.exists()


def test_migrate_refuses_non_empty_destination_without_touching_it(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    destination = tmp_path / "destination"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(MigrationConflictError):
        migrate_data(source, destination, tmp_path / "backup.zip")

    assert marker.read_text(encoding="utf-8") == "keep"
