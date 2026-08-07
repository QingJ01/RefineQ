"""Tests for owner- and project-scoped SQLite FTS search."""

from __future__ import annotations

from pathlib import Path

import pytest

from refineq.knowledge import index as index_module
from refineq.knowledge.index import KnowledgeIndex, MaterialQuotaExceededError


def test_search_is_isolated_by_owner_and_project(tmp_path: Path) -> None:
    index = KnowledgeIndex(tmp_path)
    index.add_document(
        owner_id="alice",
        project_id="calculus",
        material_id="material-1",
        filename="calculus.txt",
        text="The derivative measures the local rate of change.",
    )
    index.add_document(
        owner_id="alice",
        project_id="history",
        material_id="material-2",
        filename="history.txt",
        text="A derivative work can have its own copyright.",
    )
    index.add_document(
        owner_id="bob",
        project_id="calculus",
        material_id="material-3",
        filename="private.txt",
        text="Derivative notes belonging only to Bob.",
    )

    results = index.search(
        owner_id="alice",
        project_id="calculus",
        query="derivative",
    )

    assert [result.material_id for result in results] == ["material-1"]
    assert results[0].citation_id == "material-1#0"
    assert "local rate" in results[0].text


def test_reindexing_one_material_replaces_its_old_chunks(tmp_path: Path) -> None:
    index = KnowledgeIndex(tmp_path)
    inputs = {
        "owner_id": "owner",
        "project_id": "project",
        "material_id": "material-1",
        "filename": "notes.txt",
    }
    index.add_document(**inputs, text="Old explanation of limits.")
    index.add_document(**inputs, text="New explanation of derivatives.")

    search_scope = {"owner_id": "owner", "project_id": "project"}
    assert index.search(**search_scope, query="limits") == []
    assert len(index.search(**search_scope, query="derivatives")) == 1


def test_batch_index_validates_every_document_before_replacing_any_rows(
    tmp_path: Path,
) -> None:
    index = KnowledgeIndex(tmp_path)
    index.add_document(
        owner_id="owner",
        project_id="project",
        material_id="existing",
        filename="existing.txt",
        text="Original limits notes.",
    )

    with pytest.raises(ValueError, match="blank"):
        index.add_documents(
            owner_id="owner",
            documents=[
                index_module.MaterialDocument(
                    project_id="project",
                    material_id="replacement",
                    filename="replacement.txt",
                    text="Replacement derivatives notes.",
                ),
                index_module.MaterialDocument(
                    project_id="project",
                    material_id="broken",
                    filename="broken.txt",
                    text="",
                ),
            ],
        )

    assert [
        result.material_id
        for result in index.search(owner_id="owner", project_id="project", query="limits")
    ] == ["existing"]
    assert index.search(owner_id="owner", project_id="project", query="derivatives") == []


def test_quota_replacement_counts_only_the_material_delta(tmp_path: Path) -> None:
    index = KnowledgeIndex(tmp_path)
    index.add_document(
        owner_id="owner",
        project_id="project",
        material_id="material-1",
        filename="old.txt",
        text="Original limits notes.",
        size=20,
    )

    records = index.add_documents_with_quota(
        owner_id="owner",
        documents=[
            index_module.MaterialDocument(
                project_id="project",
                material_id="material-1",
                filename="renamed.md",
                text="Updated limits notes.",
                size=25,
            )
        ],
        max_count=1,
        max_bytes=25,
    )

    assert records[0].filename == "renamed.md"
    assert index.owner_material_usage(owner_id="owner") == (1, 25)


def test_quota_failure_preserves_the_existing_index(tmp_path: Path) -> None:
    index = KnowledgeIndex(tmp_path)
    index.add_document(
        owner_id="owner",
        project_id="project",
        material_id="material-1",
        filename="limits.txt",
        text="Original limits notes.",
        size=20,
    )

    with pytest.raises(MaterialQuotaExceededError):
        index.add_documents_with_quota(
            owner_id="owner",
            documents=[
                index_module.MaterialDocument(
                    project_id="project",
                    material_id="material-2",
                    filename="derivatives.txt",
                    text="New derivatives notes.",
                    size=10,
                )
            ],
            max_count=1,
            max_bytes=100,
        )

    assert [
        result.material_id
        for result in index.search(owner_id="owner", project_id="project", query="limits")
    ] == ["material-1"]
