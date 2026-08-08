"""Contract tests for SQL-backed owner-scoped records."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest

from refineq.database.engine import Database
from refineq.storage.json_store import (
    RecordAlreadyExistsError,
    RecordNotFoundError,
    StaleVersionError,
    StoredRecord,
)
from refineq.storage.sql_store import SqlRecordStore


@pytest.fixture
def store(tmp_path) -> SqlRecordStore:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'records.sqlite3').as_posix()}")
    database.initialize()
    return SqlRecordStore(database)


def test_records_are_isolated_by_owner_and_collection(store: SqlRecordStore) -> None:
    store.create("alice", "projects", "shared", {"name": "Alice"})
    store.create("bob", "projects", "shared", {"name": "Bob"})
    store.create("alice", "sessions", "shared", {"name": "Session"})

    assert store.read("alice", "projects", "shared").data == {"name": "Alice"}
    assert store.read("bob", "projects", "shared").data == {"name": "Bob"}
    assert store.read("alice", "sessions", "shared").data == {"name": "Session"}


def test_compare_and_swap_preserves_record_versions(store: SqlRecordStore) -> None:
    original = store.create("owner", "learning", "space", {"count": 0})
    updated = store.save(
        "owner",
        "learning",
        "space",
        {"count": 1},
        expected_version=original.version,
    )

    assert updated.version == 2
    with pytest.raises(StaleVersionError):
        store.save(
            "owner",
            "learning",
            "space",
            {"count": 2},
            expected_version=original.version,
        )


def test_mutate_serializes_concurrent_updates(store: SqlRecordStore) -> None:
    store.create("owner", "learning", "space", {"count": 0})

    def increment(_: int) -> None:
        store.mutate(
            "owner",
            "learning",
            "space",
            lambda data: {**data, "count": data["count"] + 1},
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(increment, range(16)))

    record = store.read("owner", "learning", "space")
    assert record.data["count"] == 16
    assert record.version == 17


def test_list_delete_and_missing_record_match_existing_contract(store: SqlRecordStore) -> None:
    store.create("owner", "workspaces", "one", {"name": "One"})
    store.create("owner", "workspaces", "two", {"name": "Two"})

    assert [item.data["name"] for item in store.list("owner", "workspaces")] == [
        "One",
        "Two",
    ]
    store.delete("owner", "workspaces", "one")

    with pytest.raises(RecordNotFoundError):
        store.read("owner", "workspaces", "one")


def test_restore_preserves_exact_record_without_overwriting_survivor(
    store: SqlRecordStore,
) -> None:
    deleted = StoredRecord(schema_version=3, version=7, data={"name": "Deleted"})

    restored = store.restore("owner", "workspaces", "one", deleted)

    assert restored == deleted
    assert store.read("owner", "workspaces", "one") == deleted

    survivor = store.save(
        "owner",
        "workspaces",
        "one",
        {"name": "Survivor"},
        expected_version=deleted.version,
    )
    assert store.restore("owner", "workspaces", "one", deleted) == survivor
    assert store.read("owner", "workspaces", "one") == survivor


def test_owner_transaction_is_reentrant_for_repository_quota_checks(
    store: SqlRecordStore,
) -> None:
    with store.owner_transaction("owner", "workspace-quota"):
        store.create("owner", "workspaces", "one", {"name": "One"})
        assert len(store.list("owner", "workspaces")) == 1


def test_duplicate_create_does_not_abort_an_owner_transaction(store: SqlRecordStore) -> None:
    store.create("owner", "workspaces", "one", {"name": "One"})

    with store.owner_transaction("owner", "workspace-quota"):
        with pytest.raises(RecordAlreadyExistsError):
            store.create("owner", "workspaces", "one", {"name": "Duplicate"})
        store.create("owner", "workspaces", "two", {"name": "Two"})

    assert [item.data["name"] for item in store.list("owner", "workspaces")] == [
        "One",
        "Two",
    ]


def test_nested_postgres_owner_transactions_acquire_each_scope_lock() -> None:
    class RecordingSession:
        def __init__(self) -> None:
            self.params: list[dict[str, int]] = []

        def execute(self, statement, params):
            del statement
            self.params.append(params)

    class RecordingDatabase:
        is_postgresql = True

        def __init__(self) -> None:
            self.opened = 0
            self.session_instance = RecordingSession()

        @contextmanager
        def session(self):
            self.opened += 1
            yield self.session_instance

    database = RecordingDatabase()
    nested_store = SqlRecordStore(database)  # type: ignore[arg-type]

    with (
        nested_store.owner_transaction("owner", "outer-scope"),
        nested_store.owner_transaction("owner", "inner-scope"),
    ):
        pass

    assert database.opened == 1
    assert database.session_instance.params == [
        {"key": nested_store._advisory_key("owner", "outer-scope")},
        {"key": nested_store._advisory_key("owner", "inner-scope")},
    ]
