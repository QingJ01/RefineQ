"""Versioned owner-scoped session persistence."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from refineq.storage.json_store import AtomicJsonStore, StoredRecord

SESSION_SCHEMA_VERSION = 1


class SessionRepository:
    def __init__(self, store: AtomicJsonStore) -> None:
        self._store = store

    def create(
        self,
        owner_id: str,
        session_id: str,
        data: dict[str, Any],
    ) -> StoredRecord:
        return self._store.create(
            owner_id,
            "sessions",
            session_id,
            data,
            schema_version=SESSION_SCHEMA_VERSION,
        )

    def get(self, owner_id: str, session_id: str) -> StoredRecord:
        return self._store.read(owner_id, "sessions", session_id)

    def mutate(
        self,
        owner_id: str,
        session_id: str,
        transform: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> StoredRecord:
        return self._store.mutate(owner_id, "sessions", session_id, transform)
