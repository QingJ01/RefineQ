"""Validated, atomic backups for the complete RefineQ runtime data root."""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

BACKUP_FORMAT = "refineq-backup"
BACKUP_VERSION = 1
_MANIFEST_NAME = "manifest.json"
_PAYLOAD_PREFIX = "data/"
_MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_MANAGED_BACKUP_ID = re.compile(r"\Abackup_[0-9]{8}T[0-9]{12}Z_[0-9a-f]{8}\Z")


class BackupError(RuntimeError):
    """Base class for expected backup failures."""


class BackupConflictError(BackupError):
    """Raised when a backup would overwrite an archive."""


class BackupValidationError(BackupError):
    """Raised when source data or an archive fails integrity checks."""


class ManagedBackupNotFoundError(BackupValidationError):
    """Raised when a managed backup identifier is invalid or unavailable."""


class RestoreConflictError(BackupError):
    """Raised when restore would overwrite runtime data."""


@dataclass(frozen=True, slots=True)
class BackupResult:
    archive: Path
    file_count: int
    total_bytes: int


@dataclass(frozen=True, slots=True)
class RestoreResult:
    destination: Path
    file_count: int
    total_bytes: int


@dataclass(frozen=True, slots=True)
class ManagedBackup:
    id: str
    created_at: datetime
    size: int
    file_count: int
    total_bytes: int


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_json(path: Path) -> None:
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BackupValidationError(f"Invalid JSON data: {path}") from error


def _validate_sqlite(path: Path) -> None:
    try:
        with closing(sqlite3.connect(path)) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
    except sqlite3.DatabaseError as error:
        raise BackupValidationError(f"Invalid SQLite data: {path}") from error
    if result is None or result[0] != "ok":
        raise BackupValidationError(f"SQLite integrity check failed: {path}")


def _snapshot_sqlite(source: Path, destination: Path) -> None:
    _validate_sqlite(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            closing(sqlite3.connect(source)) as source_connection,
            closing(sqlite3.connect(destination)) as destination_connection,
        ):
            source_connection.backup(destination_connection)
    except sqlite3.DatabaseError as error:
        raise BackupValidationError(f"Could not snapshot SQLite data: {source}") from error
    _validate_sqlite(destination)


def _payload_kind(path: Path) -> str:
    if path.suffix.lower() == ".json":
        return "json"
    if path.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        return "sqlite"
    return "file"


def _copy_validated(source: Path, destination: Path, *, kind: str) -> None:
    if kind == "json":
        _validate_json(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    elif kind == "sqlite":
        _snapshot_sqlite(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def create_backup(data_root: Path, archive: Path) -> BackupResult:
    """Create one verified zip archive without overwriting an existing backup."""

    source_root = data_root.expanduser().resolve()
    destination = archive.expanduser().resolve()
    if not source_root.is_dir():
        raise BackupValidationError(f"Data root is not a directory: {source_root}")
    if destination.exists():
        raise BackupConflictError(f"Backup already exists: {destination}")
    if _is_within(destination, source_root):
        raise BackupValidationError("Backup destination must be outside the data root")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_archive: Path | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="rqb-") as stage_name:
            stage_root = Path(stage_name) / "d"
            entries: list[dict[str, Any]] = []
            for source in sorted(source_root.rglob("*")):
                if not source.is_file():
                    continue
                if source.name.endswith((".tmp", "-wal", "-shm")):
                    continue
                relative = source.relative_to(source_root)
                staged = stage_root / relative
                kind = _payload_kind(source)
                _copy_validated(source, staged, kind=kind)
                entries.append(
                    {
                        "path": relative.as_posix(),
                        "kind": kind,
                        "size": staged.stat().st_size,
                        "sha256": _file_digest(staged),
                    }
                )

            manifest = {
                "format": BACKUP_FORMAT,
                "version": BACKUP_VERSION,
                "created_at": datetime.now(UTC).isoformat(),
                "files": entries,
            }
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.stem}-",
                suffix=".tmp",
                dir=destination.parent,
            )
            os.close(descriptor)
            temporary_archive = Path(temporary_name)
            with zipfile.ZipFile(
                temporary_archive,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as bundle:
                bundle.writestr(
                    _MANIFEST_NAME,
                    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
                )
                for entry in entries:
                    bundle.write(stage_root / entry["path"], _PAYLOAD_PREFIX + entry["path"])
            os.replace(temporary_archive, destination)
            temporary_archive = None
    finally:
        if temporary_archive is not None:
            temporary_archive.unlink(missing_ok=True)

    return BackupResult(
        archive=destination,
        file_count=len(entries),
        total_bytes=sum(int(entry["size"]) for entry in entries),
    )


def _safe_payload_path(value: str) -> PurePosixPath:
    if "\\" in value:
        raise BackupValidationError(f"Unsafe archive path: {value}")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise BackupValidationError(f"Unsafe archive path: {value}")
    return path


def _read_manifest(bundle: zipfile.ZipFile) -> dict[str, Any]:
    try:
        info = bundle.getinfo(_MANIFEST_NAME)
        if info.file_size > _MAX_MANIFEST_BYTES:
            raise BackupValidationError("Backup manifest is too large")
        manifest = json.loads(bundle.read(info).decode("utf-8"))
        if (
            manifest.get("format") != BACKUP_FORMAT
            or manifest.get("version") != BACKUP_VERSION
            or not isinstance(manifest.get("files"), list)
        ):
            raise BackupValidationError("Unsupported backup manifest")
        return manifest
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError, AttributeError) as error:
        raise BackupValidationError("Invalid backup manifest") from error


def _manifest_entries(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for raw in manifest["files"]:
        if not isinstance(raw, dict):
            raise BackupValidationError("Invalid backup file entry")
        try:
            relative = _safe_payload_path(raw["path"]).as_posix()
            kind = raw["kind"]
            size = raw["size"]
            checksum = raw["sha256"]
        except (KeyError, TypeError) as error:
            raise BackupValidationError("Invalid backup file entry") from error
        if (
            kind not in {"json", "sqlite", "file"}
            or not isinstance(size, int)
            or size < 0
            or not isinstance(checksum, str)
            or len(checksum) != 64
            or relative in entries
        ):
            raise BackupValidationError("Invalid backup file entry")
        entries[relative] = raw
    return entries


def _validate_member(info: zipfile.ZipInfo) -> None:
    if info.filename == _MANIFEST_NAME:
        return
    if not info.filename.startswith(_PAYLOAD_PREFIX):
        raise BackupValidationError(f"Unexpected archive member: {info.filename}")
    _safe_payload_path(info.filename.removeprefix(_PAYLOAD_PREFIX))
    file_type = (info.external_attr >> 16) & 0o170000
    if file_type == stat.S_IFLNK or info.is_dir():
        raise BackupValidationError(f"Unsupported archive member: {info.filename}")


def _extract_verified(
    bundle: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    destination: Path,
    entry: dict[str, Any],
) -> None:
    if info.file_size != entry["size"]:
        raise BackupValidationError(f"Backup size mismatch: {entry['path']}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256()
    with bundle.open(info) as source, destination.open("wb") as output:
        while block := source.read(1024 * 1024):
            digest.update(block)
            output.write(block)
    if digest.hexdigest() != entry["sha256"]:
        raise BackupValidationError(f"Backup checksum mismatch: {entry['path']}")
    if entry["kind"] == "json":
        _validate_json(destination)
    elif entry["kind"] == "sqlite":
        _validate_sqlite(destination)


def restore_backup(archive: Path, destination_root: Path) -> RestoreResult:
    """Validate an entire archive, then atomically install it into an empty root."""

    source = archive.expanduser().resolve()
    destination = destination_root.expanduser().resolve()
    if not source.is_file():
        raise BackupValidationError(f"Backup does not exist: {source}")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise RestoreConflictError(f"Restore destination is not empty: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(source) as bundle:
            infos = bundle.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise BackupValidationError("Backup contains duplicate members")
            for info in infos:
                _validate_member(info)
            manifest = _read_manifest(bundle)
            entries = _manifest_entries(manifest)
            payload_infos = {
                info.filename.removeprefix(_PAYLOAD_PREFIX): info
                for info in infos
                if info.filename != _MANIFEST_NAME
            }
            if set(payload_infos) != set(entries):
                raise BackupValidationError("Backup payload does not match its manifest")

            with tempfile.TemporaryDirectory(
                prefix="rqr-",
                dir=destination.parent,
            ) as stage_name:
                staged_data = Path(stage_name) / "d"
                staged_data.mkdir()
                for relative, entry in entries.items():
                    target = (staged_data / Path(*PurePosixPath(relative).parts)).resolve()
                    if not _is_within(target, staged_data.resolve()):
                        raise BackupValidationError(f"Unsafe restore path: {relative}")
                    _extract_verified(bundle, payload_infos[relative], target, entry)

                if destination.exists():
                    if any(destination.iterdir()):
                        raise RestoreConflictError(
                            f"Restore destination became non-empty: {destination}"
                        )
                    destination.rmdir()
                os.replace(staged_data, destination)
    except zipfile.BadZipFile as error:
        raise BackupValidationError("Backup is not a valid zip archive") from error

    return RestoreResult(
        destination=destination,
        file_count=len(entries),
        total_bytes=sum(int(entry["size"]) for entry in entries.values()),
    )


def _managed_archive(backup_root: Path, backup_id: str) -> Path:
    root = backup_root.expanduser().resolve()
    if not _MANAGED_BACKUP_ID.fullmatch(backup_id):
        raise ManagedBackupNotFoundError("Invalid managed backup ID")
    archive = (root / f"{backup_id}.zip").resolve()
    if archive.parent != root or not archive.is_file():
        raise ManagedBackupNotFoundError("Managed backup does not exist")
    return archive


def _managed_info(archive: Path) -> ManagedBackup:
    try:
        with zipfile.ZipFile(archive) as bundle:
            infos = bundle.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise BackupValidationError("Backup contains duplicate members")
            for info in infos:
                _validate_member(info)
            manifest = _read_manifest(bundle)
            entries = _manifest_entries(manifest)
            payload_names = {
                info.filename.removeprefix(_PAYLOAD_PREFIX)
                for info in infos
                if info.filename != _MANIFEST_NAME
            }
            if payload_names != set(entries):
                raise BackupValidationError("Backup payload does not match its manifest")
            created_at = datetime.fromisoformat(str(manifest["created_at"]))
            if created_at.tzinfo is None or created_at.utcoffset() is None:
                raise ValueError("created_at must be timezone-aware")
    except (KeyError, TypeError, ValueError, zipfile.BadZipFile) as error:
        raise BackupValidationError("Invalid managed backup") from error
    return ManagedBackup(
        id=archive.stem,
        created_at=created_at.astimezone(UTC),
        size=archive.stat().st_size,
        file_count=len(entries),
        total_bytes=sum(int(entry["size"]) for entry in entries.values()),
    )


def create_managed_backup(data_root: Path, backup_root: Path) -> ManagedBackup:
    """Create a backup in the server-owned backup directory and return its opaque ID."""

    root = backup_root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    backup_id = f"backup_{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}_{uuid4().hex[:8]}"
    archive = root / f"{backup_id}.zip"
    create_backup(data_root, archive)
    return _managed_info(archive)


def list_managed_backups(backup_root: Path) -> list[ManagedBackup]:
    """List only archives issued by the managed backup service."""

    root = backup_root.expanduser().resolve()
    if not root.exists():
        return []
    backups = [
        _managed_info(path)
        for path in root.iterdir()
        if path.is_file() and path.suffix == ".zip" and _MANAGED_BACKUP_ID.fullmatch(path.stem)
    ]
    return sorted(backups, key=lambda item: (item.created_at, item.id), reverse=True)


def delete_managed_backup(backup_root: Path, backup_id: str) -> None:
    """Delete one server-issued backup, primarily for failed-operation compensation."""

    archive = _managed_archive(backup_root, backup_id)
    try:
        archive.unlink()
    except OSError as error:
        raise BackupError("Managed backup cleanup failed") from error


def validate_managed_backup(backup_root: Path, backup_id: str) -> ManagedBackup:
    """Fully extract and validate one server-issued backup without changing runtime data."""

    archive = _managed_archive(backup_root, backup_id)
    info = _managed_info(archive)
    # The OS temporary root is intentionally used here. Nesting validation under
    # a deployment path can exceed the legacy Windows path limit for otherwise
    # valid owner/workspace/material keys.
    with tempfile.TemporaryDirectory(prefix="rqv-") as root:
        result = restore_backup(archive, Path(root) / "d")
    if result.file_count != info.file_count or result.total_bytes != info.total_bytes:
        raise BackupValidationError("Managed backup validation totals do not match")
    return info
