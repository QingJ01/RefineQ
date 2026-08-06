"""Owner-scoped persistence for implicit learning workspaces."""

from __future__ import annotations

from datetime import UTC, datetime

from refineq.storage.json_store import AtomicJsonStore
from refineq.workspaces.models import LearningWorkspace

WORKSPACE_SCHEMA_VERSION = 1


class WorkspaceRepository:
    def __init__(self, store: AtomicJsonStore) -> None:
        self._store = store

    def create(
        self,
        owner_id: str,
        workspace_id: str,
        *,
        title: str,
        subject: str,
        goal: str,
        topics: list[str],
        keywords: list[str],
        routing_summary: str,
        now: datetime | None = None,
    ) -> LearningWorkspace:
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        workspace = LearningWorkspace(
            id=workspace_id,
            title=title.strip(),
            subject=subject.strip(),
            goal=goal.strip(),
            topics=[item.strip() for item in topics if item.strip()],
            keywords=list(dict.fromkeys(item.strip() for item in keywords if item.strip())),
            routing_summary=routing_summary.strip(),
            created_at=observed_at,
            last_active_at=observed_at,
        )
        self._store.create(
            owner_id,
            "workspaces",
            workspace_id,
            workspace.model_dump(mode="json"),
            schema_version=WORKSPACE_SCHEMA_VERSION,
        )
        return workspace

    def get(self, owner_id: str, workspace_id: str) -> LearningWorkspace:
        record = self._store.read(owner_id, "workspaces", workspace_id)
        return LearningWorkspace.model_validate(record.data)

    def list(self, owner_id: str) -> list[LearningWorkspace]:
        workspaces = [
            LearningWorkspace.model_validate(record.data)
            for record in self._store.list(owner_id, "workspaces")
        ]
        return sorted(
            workspaces,
            key=lambda item: (item.last_active_at, item.id),
            reverse=True,
        )

    def touch(
        self,
        owner_id: str,
        workspace_id: str,
        *,
        now: datetime | None = None,
    ) -> LearningWorkspace:
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)

        def update(data: dict) -> dict:
            data["last_active_at"] = observed_at.isoformat()
            return data

        record = self._store.mutate(owner_id, "workspaces", workspace_id, update)
        return LearningWorkspace.model_validate(record.data)

