from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from inspect import getsource
from pathlib import Path

import pytest
from sqlalchemy import select

from refineq.database.engine import Database
from refineq.database.schema import mcp_evaluation_runs
from refineq.mcp.sandbox import (
    DemoBusyError,
    IdempotencyConflictError,
    McpSandboxRepository,
    RunNotFoundError,
)


def _repo(tmp_path: Path) -> tuple[Database, McpSandboxRepository]:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'mcp.sqlite3').as_posix()}")
    database.initialize()
    return database, McpSandboxRepository(
        database,
        secret="evaluation-secret-that-is-long-enough-123456",
        principal_id="evaluation",
        run_ttl=timedelta(minutes=5),
        idempotency_ttl=timedelta(days=1),
    )


def test_begin_is_replayable_and_database_stores_only_hashes(tmp_path: Path) -> None:
    database, repository = _repo(tmp_path)
    now = datetime(2026, 8, 9, 10, 0, tzinfo=UTC)

    first = repository.begin("evaluator-run-0001", now=now)
    replay = repository.begin("evaluator-run-0001", now=now + timedelta(seconds=2))

    assert replay.run_token == first.run_token
    assert replay.replayed is True
    with database.session() as session:
        row = session.execute(select(mcp_evaluation_runs)).one()
    assert row.run_id_hash != first.run_token
    assert row.client_run_key_hash != "evaluator-run-0001"
    assert first.run_token not in repr(row)


def test_only_one_non_expired_run_can_hold_the_global_slot(tmp_path: Path) -> None:
    _database, repository = _repo(tmp_path)
    now = datetime(2026, 8, 9, 10, 0, tzinfo=UTC)
    repository.begin("evaluator-run-0001", now=now)

    with pytest.raises(DemoBusyError):
        repository.begin("evaluator-run-0002", now=now)

    reclaimed = repository.begin("evaluator-run-0002", now=now + timedelta(minutes=6))
    assert reclaimed.replayed is False


def test_idempotency_result_survives_completion_and_rejects_changed_input(
    tmp_path: Path,
) -> None:
    _database, repository = _repo(tmp_path)
    now = datetime(2026, 8, 9, 10, 0, tzinfo=UTC)
    run = repository.begin("evaluator-run-0001", now=now)
    repository.activate(run.run_token, now=now)
    repository.save_idempotency(
        run.run_token,
        tool_name="refineq_submit_answer",
        key="attempt-0001",
        input_payload={"answer": "a"},
        result={"score": 100},
        now=now,
    )
    repository.complete(run.run_token, now=now)

    assert repository.get_idempotency(
        run.run_token,
        tool_name="refineq_submit_answer",
        key="attempt-0001",
        input_payload={"answer": "a"},
        now=now + timedelta(minutes=1),
    ) == {"score": 100}
    with pytest.raises(IdempotencyConflictError):
        repository.get_idempotency(
            run.run_token,
            tool_name="refineq_submit_answer",
            key="attempt-0001",
            input_payload={"answer": "different"},
            now=now + timedelta(minutes=1),
        )


def test_concurrent_same_key_creates_one_run_and_other_principals_cannot_use_it(
    tmp_path: Path,
) -> None:
    database, repository = _repo(tmp_path)

    with ThreadPoolExecutor(max_workers=20) as executor:
        runs = list(
            executor.map(
                lambda _index: repository.begin("evaluator-run-0001"),
                range(20),
            )
        )

    assert len({run.run_token for run in runs}) == 1
    assert sum(not run.replayed for run in runs) == 1
    other = McpSandboxRepository(
        database,
        secret="evaluation-secret-that-is-long-enough-123456",
        principal_id="other-evaluation-principal",
        run_ttl=timedelta(minutes=5),
        idempotency_ttl=timedelta(days=1),
    )
    repository.activate(runs[0].run_token)
    with pytest.raises(RunNotFoundError):
        other.require_active(runs[0].run_token)


def test_startup_recovery_only_releases_an_expired_seeding_run(tmp_path: Path) -> None:
    _database, repository = _repo(tmp_path)
    now = datetime(2026, 8, 9, 10, 0, tzinfo=UTC)
    interrupted = repository.begin("evaluator-run-0001", now=now)

    assert repository.recover_startup(now=now + timedelta(seconds=1)) == 0
    live_replay = repository.begin("evaluator-run-0001", now=now + timedelta(seconds=2))
    assert live_replay.replayed is True

    assert repository.recover_startup(now=now + timedelta(minutes=6)) == 1
    recovered = repository.begin("evaluator-run-0001", now=now + timedelta(minutes=6))

    assert recovered.run_token == interrupted.run_token
    assert recovered.status == "seeding"
    assert recovered.replayed is False


def test_begin_can_reclaim_its_own_expired_seeding_run_without_a_restart(tmp_path: Path) -> None:
    _database, repository = _repo(tmp_path)
    now = datetime(2026, 8, 9, 10, 0, tzinfo=UTC)
    interrupted = repository.begin("evaluator-run-0001", now=now)

    recovered = repository.begin("evaluator-run-0001", now=now + timedelta(minutes=6))

    assert recovered.run_token == interrupted.run_token
    assert recovered.status == "seeding"
    assert recovered.replayed is False


def test_concurrent_failed_run_retry_has_only_one_reset_owner(tmp_path: Path) -> None:
    _database, repository = _repo(tmp_path)
    interrupted = repository.begin("evaluator-run-0001")
    repository.fail(interrupted.run_token, error_code="injected_failure")

    with ThreadPoolExecutor(max_workers=20) as executor:
        recovered = list(
            executor.map(
                lambda _index: repository.begin("evaluator-run-0001"),
                range(20),
            )
        )

    assert len({run.run_token for run in recovered}) == 1
    assert sum(not run.replayed for run in recovered) == 1


def test_failed_run_retry_is_guarded_by_a_status_and_slot_compare_and_swap() -> None:
    source = getsource(McpSandboxRepository.begin)
    failed_retry = source.split('if existing.status == "failed":', 1)[1].split(
        'raise RunCompletedError("Use a new client_run_key for a new demo")',
        1,
    )[0]
    update_predicates = failed_retry.split(".values(", 1)[0]

    assert 'mcp_evaluation_runs.c.status == "failed"' in update_predicates
    assert "mcp_evaluation_runs.c.active_slot.is_(None)" in update_predicates
    assert "if claimed.rowcount != 1:" in failed_retry
    assert "replayed=True" in failed_retry


def test_terminal_run_rows_age_out_after_the_idempotency_window(tmp_path: Path) -> None:
    database, repository = _repo(tmp_path)
    now = datetime(2026, 8, 9, 10, 0, tzinfo=UTC)
    run = repository.begin("evaluator-run-0001", now=now)
    repository.activate(run.run_token, now=now)
    repository.complete(run.run_token, now=now)

    replacement = repository.begin(
        "evaluator-run-0001",
        now=now + timedelta(days=1, seconds=1),
    )

    with database.session() as session:
        retained_hashes = set(session.scalars(select(mcp_evaluation_runs.c.run_id_hash)))
    assert repository._run_hash(run.run_token) not in retained_hashes
    assert replacement.run_token != run.run_token
    with pytest.raises(RunNotFoundError):
        repository.require_active(run.run_token, now=now + timedelta(days=1, seconds=1))
