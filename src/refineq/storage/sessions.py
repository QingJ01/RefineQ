"""Versioned owner-scoped session persistence."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
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

    def count(self, owner_id: str) -> int:
        return len(self._store.list(owner_id, "sessions"))

    def list(self, owner_id: str) -> list[StoredRecord]:
        return self._store.list(owner_id, "sessions")

    def delete(self, owner_id: str, session_id: str) -> None:
        self._store.delete(owner_id, "sessions", session_id)

    def delete_for_workspace(self, owner_id: str, workspace_id: str) -> None:
        for _, record in self.snapshot_for_workspace(owner_id, workspace_id):
            session_id = record.data.get("session_id")
            if isinstance(session_id, str):
                self.delete(owner_id, session_id)

    def snapshot_for_workspace(
        self,
        owner_id: str,
        workspace_id: str,
    ) -> list[tuple[str, StoredRecord]]:
        snapshots: list[tuple[str, StoredRecord]] = []
        for record in self.list(owner_id):
            data = record.data
            if (data.get("workspace_id") or data.get("project_id")) != workspace_id:
                continue
            session_id = data.get("session_id")
            if isinstance(session_id, str):
                snapshots.append((session_id, record))
        return snapshots

    def restore_snapshots(
        self,
        owner_id: str,
        snapshots: list[tuple[str, StoredRecord]],
    ) -> None:
        for session_id, record in snapshots:
            self._store.restore(owner_id, "sessions", session_id, record)

    def mutate(
        self,
        owner_id: str,
        session_id: str,
        transform: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> StoredRecord:
        return self._store.mutate(owner_id, "sessions", session_id, transform)

    def quota_transaction(self, owner_id: str):
        return self._store.owner_transaction(owner_id, "session-quota")

    def conversation_transaction(self, owner_id: str, session_id: str):
        digest = sha256(session_id.encode("utf-8")).hexdigest()[:32]
        return self._store.owner_transaction(owner_id, f"agent-{digest}")
