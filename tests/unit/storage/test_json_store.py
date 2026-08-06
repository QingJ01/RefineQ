"""Tests for owner-scoped atomic JSON persistence."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from refineq.storage import json_store
from refineq.storage.json_store import (
    AtomicJsonStore,
    InvalidIdentifierError,
    StaleVersionError,
)


@pytest.mark.parametrize(
    "identifier",
    ["", ".", "..", "../owner", "owner/project", "owner\\project", "has space"],
)
def test_unsafe_identifiers_are_rejected(tmp_path: Path, identifier: str) -> None:
    store = AtomicJsonStore(tmp_path)

    with pytest.raises(InvalidIdentifierError):
        store.create(identifier, "projects", "project-1", {"name": "Calculus"})


def test_same_record_id_is_isolated_by_owner(tmp_path: Path) -> None:
    store = AtomicJsonStore(tmp_path)

    store.create("alice", "projects", "shared", {"name": "Alice project"})
    store.create("bob", "projects", "shared", {"name": "Bob project"})

    assert store.read("alice", "projects", "shared").data["name"] == "Alice project"
    assert store.read("bob", "projects", "shared").data["name"] == "Bob project"


def test_compare_and_swap_rejects_stale_versions(tmp_path: Path) -> None:
    store = AtomicJsonStore(tmp_path)
    original = store.create("owner", "projects", "project-1", {"count": 0})

    updated = store.save(
        "owner",
        "projects",
        "project-1",
        {"count": 1},
        expected_version=original.version,
    )

    assert updated.version == 2
    with pytest.raises(StaleVersionError):
        store.save(
            "owner",
            "projects",
            "project-1",
            {"count": 2},
            expected_version=original.version,
        )


def test_sixteen_concurrent_writers_are_serialized_without_lost_updates(
    tmp_path: Path,
) -> None:
    store = AtomicJsonStore(tmp_path)
    store.create("owner", "learning", "project-1", {"count": 0})

    def increment(_: int) -> None:
        store.mutate(
            "owner",
            "learning",
            "project-1",
            lambda data: {**data, "count": data["count"] + 1},
        )

    with ThreadPoolExecutor(max_workers=16) as executor:
        list(executor.map(increment, range(16)))

    record = store.read("owner", "learning", "project-1")
    assert record.data["count"] == 16
    assert record.version == 17
    assert list(tmp_path.rglob("*.tmp")) == []


def test_every_record_has_an_explicit_schema_version(tmp_path: Path) -> None:
    store = AtomicJsonStore(tmp_path)

    record = store.create(
        "owner",
        "projects",
        "project-1",
        {"name": "Calculus"},
        schema_version=3,
    )

    assert record.schema_version == 3


def test_transient_windows_replace_denial_is_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = AtomicJsonStore(tmp_path)
    monkeypatch.setattr(json_store, "_IS_WINDOWS", True)
    real_replace = os.replace
    attempts = 0

    def transient_replace(source: Path, destination: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError(5, "transient file lock", str(destination))
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", transient_replace)

    record = store.create("owner", "projects", "project-1", {"name": "Calculus"})

    assert attempts == 2
    assert record.version == 1
    assert store.read("owner", "projects", "project-1").data["name"] == "Calculus"
