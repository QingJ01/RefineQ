"""Hybrid lexical and pgvector-compatible retrieval tests."""

from __future__ import annotations

from refineq.database.engine import Database
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
