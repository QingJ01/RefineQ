"""Tests for owner- and project-scoped SQLite FTS search."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from refineq.database.schema import material_chunks
from refineq.knowledge import index as index_module
from refineq.knowledge.index import (
    KnowledgeIndex,
    MaterialQuotaExceededError,
    _postgres_cosine_distance,
)


def test_postgres_vector_distance_uses_a_vector_typed_expression() -> None:
    distance = _postgres_cosine_distance(material_chunks.c.embedding, [1.0, 0.0])

    statement = select(distance.label("distance"))
    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "material_chunks.embedding <=>" in compiled
    assert "CAST(" not in compiled
    assert "<=>" in compiled


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


def test_search_matches_chinese_topic_terms_without_whitespace(tmp_path: Path) -> None:
    index = KnowledgeIndex(tmp_path)
    index.add_document(
        owner_id="learner",
        project_id="computer-architecture",
        material_id="pipeline-notes",
        filename="pipeline.txt",
        text="流水线重叠执行多条指令的不同阶段，数据冒险可用转发或停顿处理。",
    )

    results = index.search(
        owner_id="learner",
        project_id="computer-architecture",
        query="流水线与冒险",
    )

    assert [result.material_id for result in results] == ["pipeline-notes"]


def test_chunk_overlap_keeps_a_fact_that_crosses_a_hard_window_boundary(
    tmp_path: Path,
) -> None:
    index = KnowledgeIndex(tmp_path, chunk_chars=60)
    fact = "BLUE ORCHID identifies the release"
    text = f"{'x' * 54} {fact}. The remaining explanation follows."

    chunks = index._chunks(text)

    assert len(chunks) >= 2
    assert all(len(chunk) <= 60 for chunk in chunks)
    assert any(fact in chunk for chunk in chunks)


def test_chunk_size_must_guarantee_forward_progress(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="chunk_chars"):
        KnowledgeIndex(tmp_path, chunk_chars=0)


def test_chunks_prefer_a_sentence_boundary_near_the_window_end(tmp_path: Path) -> None:
    index = KnowledgeIndex(tmp_path, chunk_chars=50)

    chunks = index._chunks(f"{'a' * 35}. {'b' * 45}")

    assert chunks[0].endswith(".")


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


def test_material_metadata_can_be_updated_filtered_and_sorted(tmp_path: Path) -> None:
    index = KnowledgeIndex(tmp_path)
    index.add_document(
        owner_id="owner",
        project_id="project",
        material_id="material-b",
        filename="zeta.txt",
        text="Limits notes.",
        size=20,
    )
    index.add_document(
        owner_id="owner",
        project_id="project",
        material_id="material-a",
        filename="alpha.txt",
        text="Derivative notes.",
        size=10,
    )

    updated = index.update_material_metadata(
        owner_id="owner",
        project_id="project",
        material_id="material-b",
        title="Calculus handbook",
        tags=["Exam", "calculus"],
    )
    index.update_material_metadata(
        owner_id="owner",
        project_id="project",
        material_id="material-a",
        title="Derivative primer",
        tags=["calculus"],
    )

    assert updated.title == "Calculus handbook"
    assert updated.tags == ["Exam", "calculus"]
    assert [
        material.id
        for material in index.list_materials(
            owner_id="owner",
            project_id="project",
            status="indexed",
            tag="CALCULUS",
            sort="title",
        )
    ] == ["material-b", "material-a"]


def test_bulk_material_delete_is_atomic_and_owner_scoped(tmp_path: Path) -> None:
    index = KnowledgeIndex(tmp_path)
    for owner_id in ("alice", "bob"):
        index.add_document(
            owner_id=owner_id,
            project_id="project",
            material_id="shared-id",
            filename=f"{owner_id}.txt",
            text=f"{owner_id} private notes.",
            storage_key=f"objects/{owner_id}",
        )

    deleted = index.delete_materials(
        owner_id="alice",
        project_id="project",
        material_ids=["shared-id"],
    )

    assert [record.id for record, _ in deleted] == ["shared-id"]
    assert index.list_materials(owner_id="alice", project_id="project") == []
    assert [
        material.filename for material in index.list_materials(owner_id="bob", project_id="project")
    ] == ["bob.txt"]
