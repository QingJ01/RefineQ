"""Optional smoke test against a real PostgreSQL + pgvector instance."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from refineq.database.engine import Database

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
            index_names = set(
                connection.scalars(
                    text("SELECT indexname FROM pg_indexes WHERE tablename = 'material_chunks'")
                )
            )
        assert "ix_material_chunks_content_fts" in index_names
        assert "ix_material_chunks_embedding_hnsw" in index_names
    finally:
        database.close()
