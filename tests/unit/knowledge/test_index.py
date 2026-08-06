"""Tests for owner- and project-scoped SQLite FTS search."""

from __future__ import annotations

from pathlib import Path

from refineq.knowledge.index import KnowledgeIndex


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
