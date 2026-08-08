"""The hackathon demo seed is deterministic and never resets learner progress."""

from __future__ import annotations

import sys
from pathlib import Path

from refineq.database.engine import Database
from refineq.operations.demo import seed_demo
from refineq.storage.learning import LearningRepository
from refineq.storage.sql_store import SqlRecordStore
from refineq.storage.workspaces import WorkspaceRepository
from scripts.seed_demo import main as seed_demo_main


def test_seed_demo_uses_supplied_database_and_is_idempotent(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'runtime.sqlite3').as_posix()}")
    database.initialize()

    first = seed_demo(
        database,
        data_root,
        email="demo@example.com",
        password="correct-horse-battery-staple",
    )
    store = SqlRecordStore(database)
    first_record = LearningRepository(store).get(
        first.owner_id,
        first.workspace_id,
    )
    second = seed_demo(
        database,
        data_root,
        email="demo@example.com",
        password="correct-horse-battery-staple",
    )
    second_record = LearningRepository(store).get(
        second.owner_id,
        second.workspace_id,
    )

    assert second == first
    assert second_record.version == first_record.version
    assert second_record.data["progress"]["diagnostic_runs"] == ["demo-diagnostic"]
    assert len(second_record.data["attempts"]) == 1
    assert second_record.data["progress"]["plan"] is not None
    assert (
        WorkspaceRepository(store)
        .get(
            first.owner_id,
            first.workspace_id,
        )
        .title
        == "Calculus Sprint"
    )
    assert not (data_root / "users" / first.owner_id / "projects").exists()
    assert not (data_root / "system" / "refineq.sqlite3").exists()
    database.close()


def test_seed_demo_command_requires_runtime_password(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("REFINEQ_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.delenv("REFINEQ_DEMO_PASSWORD", raising=False)
    monkeypatch.setattr(sys, "argv", ["seed_demo.py"])

    try:
        seed_demo_main()
    except SystemExit as error:
        assert "REFINEQ_DEMO_PASSWORD" in str(error)
    else:
        raise AssertionError("seed command accepted a missing demo password")


def test_seed_demo_command_does_not_print_runtime_password(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    password = "correct-horse-battery-staple"
    monkeypatch.setenv("REFINEQ_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("REFINEQ_DEMO_EMAIL", "demo@example.com")
    monkeypatch.setenv("REFINEQ_DEMO_PASSWORD", password)
    monkeypatch.delenv("REFINEQ_DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", ["seed_demo.py"])

    seed_demo_main()

    output = capsys.readouterr().out
    assert "demo@example.com" in output
    assert password not in output
