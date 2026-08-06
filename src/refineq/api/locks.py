"""Small keyed async locks for owner-scoped API commit boundaries."""

from __future__ import annotations

from asyncio import Lock
from threading import Lock as ThreadLock


class KeyedAsyncLockPool:
    """Return one event-loop lock per stable owner/scope key."""

    def __init__(self) -> None:
        self._locks: dict[str, Lock] = {}
        self._guard = ThreadLock()

    def get(self, key: str) -> Lock:
        with self._guard:
            return self._locks.setdefault(key, Lock())
