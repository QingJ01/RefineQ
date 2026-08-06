"""Owner-scoped project persistence."""

from __future__ import annotations

from datetime import UTC, datetime

from refineq.storage.json_store import AtomicJsonStore, StoredRecord

PROJECT_SCHEMA_VERSION = 1


class ProjectRepository:
    def __init__(self, store: AtomicJsonStore) -> None:
        self._store = store

    def create(self, owner_id: str, project_id: str, *, name: str) -> StoredRecord:
        name = name.strip()
        if not name:
            raise ValueError("project name must not be blank")
        return self._store.create(
            owner_id,
            "projects",
            project_id,
            {
                "id": project_id,
                "name": name,
                "created_at": datetime.now(UTC).isoformat(),
            },
            schema_version=PROJECT_SCHEMA_VERSION,
        )

    def get(self, owner_id: str, project_id: str) -> StoredRecord:
        return self._store.read(owner_id, "projects", project_id)

    def count(self, owner_id: str) -> int:
        return len(self._store.list(owner_id, "projects"))

    def quota_transaction(self, owner_id: str):
        return self._store.owner_transaction(owner_id, "project-quota")
