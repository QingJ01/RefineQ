"""Durable filesystem primitives for crash-recovery journals."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO


def fsync_directory(path: Path) -> None:
    """Persist directory entries on platforms that support directory fsync."""

    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_mkdir(path: Path) -> None:
    """Create a directory tree and sync every newly-added directory entry."""

    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        cursor = cursor.parent
    path.mkdir(parents=True, exist_ok=True)
    for created in reversed(missing):
        fsync_directory(created.parent)


def durable_atomic_bytes(path: Path, payload: bytes) -> None:
    """Atomically replace a file and persist both data and its directory entry."""

    durable_mkdir(path.parent)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}-",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def durable_remove_tree(path: Path) -> None:
    """Remove a recovery directory and persist its removal."""

    parent = path.parent
    shutil.rmtree(path)
    fsync_directory(parent)


class RecoveryLease:
    """A process-scoped, non-blocking lease backed by an operating-system lock."""

    def __init__(self, path: Path, handle: BinaryIO) -> None:
        self.path = path
        self._handle = handle

    @classmethod
    def acquire(cls, path: Path) -> RecoveryLease | None:
        durable_mkdir(path.parent)
        created = not path.exists()
        handle = path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"1")
                handle.flush()
                os.fsync(handle.fileno())
            if created:
                fsync_directory(path.parent)
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    handle.close()
                    return None
            else:
                import fcntl

                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    handle.close()
                    return None
            return cls(path, handle)
        except Exception:
            handle.close()
            raise

    def release(self) -> None:
        if self._handle.closed:
            return
        self._handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()

    def __enter__(self) -> RecoveryLease:
        return self

    def __exit__(self, *args: object) -> None:
        del args
        self.release()
