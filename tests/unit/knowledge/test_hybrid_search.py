"""Hybrid lexical and pgvector-compatible retrieval tests."""

from __future__ import annotations

import logging

from sqlalchemy import func, select

from refineq.database.engine import Database
from refineq.database.schema import material_chunks
from refineq.knowledge.index import KnowledgeIndex


class FakeEmbedder:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self.vectors = vectors

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.vectors[text] for text in texts]


class FailingEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        del texts
        raise RuntimeError("embedding provider unavailable")


class RecordingEmbedder:
    def __init__(self, *, fail_call: int | None = None) -> None:
        self.calls: list[list[str]] = []
        self.fail_call = fail_call

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.fail_call == len(self.calls):
            raise RuntimeError("provider failed with sk-should-never-be-logged")
        return [[float(len(text)), 1.0] for text in texts]


def _database(tmp_path) -> Database:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'knowledge.sqlite3').as_posix()}")
    database.initialize()
    return database


def test_semantic_similarity_can_retrieve_a_chunk_without_shared_words(tmp_path) -> None:
    semantic = "Plants convert light into stored chemical energy."
    lexical = "Plant taxonomy names and classification rules."
    query = "plant photosynthesis"
    index = KnowledgeIndex(
        _database(tmp_path),
        embedder=FakeEmbedder(
            {
                semantic: [1.0, 0.0],
                lexical: [0.0, 1.0],
                query: [1.0, 0.0],
            }
        ),
    )
    index.add_document(
        owner_id="owner",
        project_id="biology",
        material_id="semantic",
        filename="energy.txt",
        text=semantic,
    )
    index.add_document(
        owner_id="owner",
        project_id="biology",
        material_id="lexical",
        filename="taxonomy.txt",
        text=lexical,
    )

    results = index.search(
        owner_id="owner",
        project_id="biology",
        query=query,
        limit=2,
    )

    assert results[0].material_id == "semantic"
    assert results[0].score > results[1].score


def test_embedding_failure_keeps_lexical_retrieval_available(tmp_path) -> None:
    index = KnowledgeIndex(_database(tmp_path), embedder=FailingEmbedder())
    index.add_document(
        owner_id="owner",
        project_id="calculus",
        material_id="limits",
        filename="limits.txt",
        text="A limit describes the value approached by a function.",
    )

    results = index.search(
        owner_id="owner",
        project_id="calculus",
        query="limit",
    )

    assert [result.material_id for result in results] == ["limits"]


def test_document_embeddings_are_sent_in_bounded_batches(tmp_path) -> None:
    embedder = RecordingEmbedder()
    database = _database(tmp_path)
    index = KnowledgeIndex(database, chunk_chars=12, embedder=embedder, embedding_batch_size=64)
    text = "\n".join(f"chunk-{number:03d}" for number in range(130))

    index.add_document(
        owner_id="owner",
        project_id="project",
        material_id="large",
        filename="large.txt",
        text=text,
    )

    assert [len(call) for call in embedder.calls] == [64, 64, 2]


def test_failed_embedding_batch_is_logged_safely_and_other_batches_are_kept(
    tmp_path,
    caplog,
) -> None:
    embedder = RecordingEmbedder(fail_call=2)
    database = _database(tmp_path)
    index = KnowledgeIndex(database, chunk_chars=12, embedder=embedder, embedding_batch_size=2)

    with caplog.at_level(logging.WARNING):
        index.add_document(
            owner_id="owner",
            project_id="project",
            material_id="partial",
            filename="partial.txt",
            text="chunk-000\nchunk-001\nchunk-002\nchunk-003\nchunk-004",
        )

    with database.session() as session:
        embedded = session.scalar(
            select(func.count())
            .select_from(material_chunks)
            .where(material_chunks.c.embedding.is_not(None))
        )
        missing = session.scalar(
            select(func.count())
            .select_from(material_chunks)
            .where(material_chunks.c.embedding.is_(None))
        )
    assert embedded == 3
    assert missing == 2
    assert "RuntimeError" in caplog.text
    assert "sk-should-never-be-logged" not in caplog.text


def test_missing_embeddings_can_be_backfilled_without_reuploading_material(tmp_path) -> None:
    database = _database(tmp_path)
    index = KnowledgeIndex(database, chunk_chars=12)
    index.add_document(
        owner_id="owner",
        project_id="project",
        material_id="legacy",
        filename="legacy.txt",
        text="chunk-000\nchunk-001\nchunk-002",
    )
    embedder = RecordingEmbedder()
    index.embedder = embedder

    updated = index.backfill_embeddings()

    with database.session() as session:
        missing = session.scalar(
            select(func.count())
            .select_from(material_chunks)
            .where(material_chunks.c.embedding.is_(None))
        )
    assert updated == 3
    assert missing == 0
