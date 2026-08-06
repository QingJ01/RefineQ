"""Backup-first relocation of a validated RefineQ runtime data root."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from refineq.operations.backup import BackupResult, RestoreResult, create_backup, restore_backup


class MigrationError(RuntimeError):
    """Base class for expected migration failures."""


class MigrationConflictError(MigrationError):
    """Raised before migration could overwrite an existing runtime."""


@dataclass(frozen=True, slots=True)
class MigrationResult:
    backup: BackupResult
    restore: RestoreResult


def migrate_data(
    source_root: Path,
    destination_root: Path,
    backup_archive: Path,
) -> MigrationResult:
    """Validate and back up a source before installing it into an empty destination."""

    source = source_root.expanduser().resolve()
    destination = destination_root.expanduser().resolve()
    if source == destination:
        raise MigrationConflictError("Source and destination must be different")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise MigrationConflictError(f"Migration destination is not empty: {destination}")

    backup = create_backup(source, backup_archive)
    restore = restore_backup(backup.archive, destination)
    return MigrationResult(backup=backup, restore=restore)
