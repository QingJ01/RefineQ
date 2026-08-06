"""Atomic, versioned JSON records scoped below one owner directory."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, RLock
from typing import Any

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_IS_WINDOWS = os.name == "nt"


class StorageError(RuntimeError):
    """Base class for expected persistence failures."""


class InvalidIdentifierError(StorageError):
    """Raised before an unsafe value can participate in a path."""


class RecordNotFoundError(StorageError):
    """Raised when an owner-scoped record does not exist."""


class RecordAlreadyExistsError(StorageError):
    """Raised when create would overwrite an existing record."""


class StaleVersionError(StorageError):
    """Raised when compare-and-swap detects a lost update."""


@dataclass(frozen=True, slots=True)
class StoredRecord:
    schema_version: int
    version: int
    data: dict[str, Any]


def validate_identifier(value: str, *, field: str = "identifier") -> str:
    normalized = value.strip()
    if normalized != value or not _SAFE_IDENTIFIER.fullmatch(normalized):
        raise InvalidIdentifierError(f"Unsafe {field}: {value!r}")
    return normalized


def _replace_with_retry(source: Path, destination: Path) -> None:
    """Tolerate brief Windows file locks without weakening atomic replacement."""

    for attempt in range(4):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if not _IS_WINDOWS or attempt == 3:
                raise
            time.sleep(0.01 * (2**attempt))


class AtomicJsonStore:
    """Persist small records with atomic replacement and process-local locking."""

    _locks_guard = Lock()
    _locks: dict[str, RLock] = {}

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root.expanduser().resolve()

    @classmethod
    def _lock_for(cls, path: Path) -> RLock:
        key = os.path.normcase(str(path))
        with cls._locks_guard:
            return cls._locks.setdefault(key, RLock())

    def _record_path(self, owner_id: str, collection: str, record_id: str) -> Path:
        owner_id = validate_identifier(owner_id, field="owner_id")
        collection = validate_identifier(collection, field="collection")
        record_id = validate_identifier(record_id, field="record_id")
        owner_root = (self.data_root / "users" / owner_id).resolve()
        path = (owner_root / collection / f"{record_id}.json").resolve()
        try:
            path.relative_to(owner_root)
        except ValueError as error:
            raise InvalidIdentifierError("Record path escaped the owner scope") from error
        return path

    @staticmethod
    def _deserialize(path: Path) -> StoredRecord:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            schema_version = int(raw["schema_version"])
            version = int(raw["version"])
            data = raw["data"]
            if schema_version < 1 or version < 1 or not isinstance(data, dict):
                raise ValueError("invalid record envelope")
        except FileNotFoundError as error:
            raise RecordNotFoundError(str(path)) from error
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise StorageError(f"Invalid record envelope: {path}") from error
        return StoredRecord(
            schema_version=schema_version,
            version=version,
            data=deepcopy(data),
        )

    @staticmethod
    def _serialize(record: StoredRecord) -> bytes:
        return json.dumps(
            {
                "schema_version": record.schema_version,
                "version": record.version,
                "data": record.data,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")

    def _write_unlocked(self, path: Path, record: StoredRecord) -> None:
        payload = self._serialize(record)
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.stem}-",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as temporary_file:
                temporary_file.write(payload)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            _replace_with_retry(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def create(
        self,
        owner_id: str,
        collection: str,
        record_id: str,
        data: dict[str, Any],
        *,
        schema_version: int = 1,
    ) -> StoredRecord:
        if schema_version < 1:
            raise ValueError("schema_version must be positive")
        path = self._record_path(owner_id, collection, record_id)
        with self._lock_for(path):
            if path.exists():
                raise RecordAlreadyExistsError(str(path))
            record = StoredRecord(schema_version, 1, deepcopy(data))
            self._write_unlocked(path, record)
            return record

    def read(self, owner_id: str, collection: str, record_id: str) -> StoredRecord:
        path = self._record_path(owner_id, collection, record_id)
        with self._lock_for(path):
            return self._deserialize(path)

    def save(
        self,
        owner_id: str,
        collection: str,
        record_id: str,
        data: dict[str, Any],
        *,
        expected_version: int,
    ) -> StoredRecord:
        path = self._record_path(owner_id, collection, record_id)
        with self._lock_for(path):
            current = self._deserialize(path)
            if current.version != expected_version:
                raise StaleVersionError(
                    f"Expected version {expected_version}, found {current.version}"
                )
            updated = StoredRecord(
                current.schema_version,
                current.version + 1,
                deepcopy(data),
            )
            self._write_unlocked(path, updated)
            return updated

    def mutate(
        self,
        owner_id: str,
        collection: str,
        record_id: str,
        transform: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> StoredRecord:
        """Apply one serialized read-modify-write transaction."""

        path = self._record_path(owner_id, collection, record_id)
        with self._lock_for(path):
            current = self._deserialize(path)
            data = transform(deepcopy(current.data))
            if not isinstance(data, dict):
                raise TypeError("record transform must return a dictionary")
            updated = StoredRecord(
                current.schema_version,
                current.version + 1,
                deepcopy(data),
            )
            self._write_unlocked(path, updated)
            return updated
