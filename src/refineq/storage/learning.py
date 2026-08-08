"""Idempotent persistence for personal learning-space state."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from refineq.storage.json_store import (
    AtomicJsonStore,
    RecordAlreadyExistsError,
    RecordNotFoundError,
    StoredRecord,
    validate_identifier,
)

LEARNING_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class AttemptWriteResult:
    record: StoredRecord
    attempt: dict[str, Any]
    replayed: bool


class LearningRepository:
    def __init__(self, store: AtomicJsonStore) -> None:
        self._store = store

    def get_or_create(self, owner_id: str, project_id: str) -> StoredRecord:
        try:
            return self._store.read(owner_id, "learning", project_id)
        except RecordNotFoundError:
            try:
                return self._store.create(
                    owner_id,
                    "learning",
                    project_id,
                    {"workspace_id": project_id, "attempts": {}, "progress": {}},
                    schema_version=LEARNING_SCHEMA_VERSION,
                )
            except RecordAlreadyExistsError:
                return self._store.read(owner_id, "learning", project_id)

    def get(self, owner_id: str, project_id: str) -> StoredRecord:
        return self._store.read(owner_id, "learning", project_id)

    def delete(self, owner_id: str, project_id: str) -> None:
        self._store.delete(owner_id, "learning", project_id)

    def mutate(
        self,
        owner_id: str,
        project_id: str,
        transform: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> StoredRecord:
        self.get_or_create(owner_id, project_id)
        return self._store.mutate(owner_id, "learning", project_id, transform)

    def question_transaction(self, owner_id: str, project_id: str):
        """Serialize question generation so retries cannot duplicate model work."""

        project_id = validate_identifier(project_id, field="project_id")
        return self._store.owner_transaction(owner_id, f"question-{project_id}")

    def record_attempt(
        self,
        owner_id: str,
        project_id: str,
        *,
        attempt_id: str,
        attempt: dict[str, Any],
    ) -> AttemptWriteResult:
        attempt_id = validate_identifier(attempt_id, field="attempt_id")
        self.get_or_create(owner_id, project_id)
        replayed = False

        def add_once(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal replayed
            attempts = data.setdefault("attempts", {})
            if attempt_id in attempts:
                replayed = True
                return data
            attempts[attempt_id] = deepcopy(attempt)
            return data

        record = self._store.mutate(
            owner_id,
            "learning",
            project_id,
            add_once,
        )
        return AttemptWriteResult(
            record=record,
            attempt=deepcopy(record.data["attempts"][attempt_id]),
            replayed=replayed,
        )
