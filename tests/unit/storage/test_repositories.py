"""Tests for typed storage repositories."""

from __future__ import annotations

from pathlib import Path

from refineq.storage.json_store import AtomicJsonStore, RecordNotFoundError
from refineq.storage.learning import LearningRepository
from refineq.storage.projects import ProjectRepository
from refineq.storage.sessions import SessionRepository


def test_project_repository_never_crosses_owner_scope(tmp_path: Path) -> None:
    projects = ProjectRepository(AtomicJsonStore(tmp_path))
    projects.create("alice", "project-1", name="Alice calculus")

    try:
        projects.get("bob", "project-1")
    except RecordNotFoundError:
        pass
    else:
        raise AssertionError("Bob must not be able to read Alice's project")


def test_attempt_writes_are_idempotent(tmp_path: Path) -> None:
    learning = LearningRepository(AtomicJsonStore(tmp_path))

    first = learning.record_attempt(
        "owner",
        "project-1",
        attempt_id="attempt-1",
        attempt={"is_correct": True, "question_id": "question-1"},
    )
    replay = learning.record_attempt(
        "owner",
        "project-1",
        attempt_id="attempt-1",
        attempt={"is_correct": False, "question_id": "question-1"},
    )

    assert first.replayed is False
    assert replay.replayed is True
    assert replay.attempt == first.attempt
    assert len(replay.record.data["attempts"]) == 1
    assert replay.record.data["workspace_id"] == "project-1"
    assert "project_id" not in replay.record.data


def test_session_repository_persists_versioned_session_data(tmp_path: Path) -> None:
    sessions = SessionRepository(AtomicJsonStore(tmp_path))

    created = sessions.create(
        "owner",
        "session-1",
        {"project_id": "project-1", "stage": "diagnostic"},
    )
    loaded = sessions.get("owner", "session-1")

    assert created.schema_version == 1
    assert loaded.data == created.data
