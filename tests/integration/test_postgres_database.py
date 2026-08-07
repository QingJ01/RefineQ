"""Optional smoke test against a real PostgreSQL + pgvector instance."""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import delete, text

from refineq.database.engine import Database
from refineq.database.schema import material_chunks, materials, records
from refineq.knowledge.index import (
    KnowledgeIndex,
    MaterialDocument,
    MaterialQuotaExceededError,
)
from refineq.storage.sql_store import SqlRecordStore

_DATABASE_URL = os.environ.get("REFINEQ_TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _DATABASE_URL,
    reason="REFINEQ_TEST_DATABASE_URL is not configured",
)


def test_postgres_schema_enables_vector_extension_and_indexes() -> None:
    database = Database(_DATABASE_URL)
    database.initialize()
    try:
        with database.engine.connect() as connection:
            assert connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            )
            assert connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm')")
            )
            index_names = set(
                connection.scalars(
                    text("SELECT indexname FROM pg_indexes WHERE tablename = 'material_chunks'")
                )
            )
        assert "ix_material_chunks_content_fts" in index_names
        assert "ix_material_chunks_content_trgm" in index_names
        assert "ix_material_chunks_embedding_hnsw" in index_names
    finally:
        database.close()


class _PostgresEmbedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for value in texts:
            vector = [0.0] * 1536
            if "chemical energy" in value or "photosynthesis" in value:
                vector[0] = 1.0
            else:
                vector[1] = 1.0
            vectors.append(vector)
        return vectors


def _clear_owner(database: Database, owner_id: str) -> None:
    with database.session() as session:
        session.execute(delete(material_chunks).where(material_chunks.c.owner_id == owner_id))
        session.execute(delete(materials).where(materials.c.owner_id == owner_id))
        session.execute(delete(records).where(records.c.owner_id == owner_id))


def test_postgres_executes_indexed_chinese_lexical_and_vector_search() -> None:
    database = Database(_DATABASE_URL)
    database.initialize()
    owner_id = "postgres_search_owner"
    _clear_owner(database, owner_id)
    try:
        lexical_index = KnowledgeIndex(database)
        lexical_index.add_document(
            owner_id=owner_id,
            project_id="math",
            material_id="limits",
            filename="limits.md",
            text="函数极限描述函数值逐渐逼近的目标。",
        )
        lexical_results = lexical_index.search(
            owner_id=owner_id,
            project_id="math",
            query="函数极限",
        )

        semantic_index = KnowledgeIndex(database, embedder=_PostgresEmbedder())
        semantic_index.add_document(
            owner_id=owner_id,
            project_id="biology",
            material_id="energy",
            filename="energy.md",
            text="Plants convert light into stored chemical energy.",
        )
        semantic_results = semantic_index.search(
            owner_id=owner_id,
            project_id="biology",
            query="photosynthesis",
        )

        assert [result.material_id for result in lexical_results] == ["limits"]
        assert [result.material_id for result in semantic_results] == ["energy"]
    finally:
        _clear_owner(database, owner_id)
        database.close()


def test_postgres_jsonb_round_trip_and_cross_connection_quota_lock() -> None:
    database = Database(_DATABASE_URL)
    database.initialize()
    owner_id = "postgres_quota_owner"
    _clear_owner(database, owner_id)
    try:
        store = SqlRecordStore(database)
        store.create(owner_id, "workspaces", "space", {"nested": {"value": 1}})
        with database.engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT pg_typeof(data)::text FROM records "
                        "WHERE owner_id = :owner_id AND record_id = 'space'"
                    ),
                    {"owner_id": owner_id},
                )
                == "jsonb"
            )

        index = KnowledgeIndex(database)
        index.add_documents_with_quota(
            owner_id=owner_id,
            documents=[
                MaterialDocument(
                    project_id="space",
                    material_id="existing",
                    filename="existing.txt",
                    text="Existing notes",
                    size=10,
                )
            ],
            max_count=1,
            max_bytes=100,
        )
        blocker = database.engine.connect()
        transaction = blocker.begin()
        blocker.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:owner_id, 0))"),
            {"owner_id": owner_id},
        )
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                pending = executor.submit(
                    index.add_documents_with_quota,
                    owner_id=owner_id,
                    documents=[
                        MaterialDocument(
                            project_id="space",
                            material_id="second",
                            filename="second.txt",
                            text="Second notes",
                            size=10,
                        )
                    ],
                    max_count=1,
                    max_bytes=100,
                )
                time.sleep(0.2)
                assert pending.done() is False
                transaction.rollback()
                with pytest.raises(MaterialQuotaExceededError):
                    pending.result(timeout=5)
        finally:
            if transaction.is_active:
                transaction.rollback()
            blocker.close()
    finally:
        _clear_owner(database, owner_id)
        database.close()
