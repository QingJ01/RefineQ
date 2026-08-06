"""The hackathon demo seed is deterministic and never resets learner progress."""

from __future__ import annotations

from pathlib import Path

from refineq.operations.demo import seed_demo
from refineq.storage.json_store import AtomicJsonStore
from refineq.storage.learning import LearningRepository
from refineq.storage.workspaces import WorkspaceRepository


def test_seed_demo_is_complete_and_idempotent(tmp_path: Path) -> None:
    data_root = tmp_path / "data"

    first = seed_demo(data_root)
    first_record = LearningRepository(AtomicJsonStore(data_root)).get(
        first.owner_id,
        first.workspace_id,
    )
    second = seed_demo(data_root)
    second_record = LearningRepository(AtomicJsonStore(data_root)).get(
        second.owner_id,
        second.workspace_id,
    )

    assert second == first
    assert second_record.version == first_record.version
    assert second_record.data["progress"]["diagnostic_runs"] == ["demo-diagnostic"]
    assert len(second_record.data["attempts"]) == 1
    assert second_record.data["progress"]["plan"] is not None
    assert (
        WorkspaceRepository(AtomicJsonStore(data_root))
        .get(
            first.owner_id,
            first.workspace_id,
        )
        .title
        == "Calculus Sprint"
    )
    assert not (data_root / "users" / first.owner_id / "projects").exists()
    assert (data_root / "users" / first.owner_id / "knowledge" / "search.sqlite3").is_file()
