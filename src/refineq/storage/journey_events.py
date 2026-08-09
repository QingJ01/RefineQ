"""Owner/workspace-scoped product journey events isolated from learning state."""

from __future__ import annotations

from refineq.learning.events import JourneyEvent, append_journey_event
from refineq.storage.json_store import (
    AtomicJsonStore,
    RecordAlreadyExistsError,
    RecordNotFoundError,
    StoredRecord,
)

JOURNEY_EVENT_SCHEMA_VERSION = 1


class JourneyEventRepository:
    def __init__(self, store: AtomicJsonStore) -> None:
        self._store = store

    def _get_or_create(self, owner_id: str, workspace_id: str) -> StoredRecord:
        try:
            return self._store.read(owner_id, "journey_events", workspace_id)
        except RecordNotFoundError:
            try:
                return self._store.create(
                    owner_id,
                    "journey_events",
                    workspace_id,
                    {"workspace_id": workspace_id, "events": []},
                    schema_version=JOURNEY_EVENT_SCHEMA_VERSION,
                )
            except RecordAlreadyExistsError:
                return self._store.read(owner_id, "journey_events", workspace_id)

    @staticmethod
    def _find(data: dict, event_id: str) -> JourneyEvent | None:
        return next(
            (
                JourneyEvent.model_validate(item)
                for item in data.get("events", [])
                if item.get("id") == event_id
            ),
            None,
        )

    def append(
        self,
        owner_id: str,
        workspace_id: str,
        event: JourneyEvent,
    ) -> JourneyEvent:
        if event.workspace_id != workspace_id:
            raise ValueError("Journey event workspace does not match its record")
        current = self._get_or_create(owner_id, workspace_id)
        existing = self._find(current.data, event.id)
        if existing is not None:
            return existing
        selected = event

        def add_once(data: dict) -> dict:
            nonlocal selected
            concurrent = self._find(data, event.id)
            if concurrent is not None:
                selected = concurrent
                return data
            container = {"journey_events": data.setdefault("events", [])}
            append_journey_event(container, event)
            return data

        self._store.mutate(owner_id, "journey_events", workspace_id, add_once)
        return selected

    def list(self, owner_id: str, workspace_id: str) -> list[JourneyEvent]:
        try:
            record = self._store.read(owner_id, "journey_events", workspace_id)
        except RecordNotFoundError:
            return []
        return [JourneyEvent.model_validate(item) for item in record.data.get("events", [])]

    def delete(self, owner_id: str, workspace_id: str) -> None:
        self._store.delete(owner_id, "journey_events", workspace_id)
