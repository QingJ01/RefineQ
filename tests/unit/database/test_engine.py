"""Database engine and schema lifecycle tests."""

from __future__ import annotations

from sqlalchemy import inspect, select, text

from refineq.database.engine import Database
from refineq.database.schema import SCHEMA_VERSION, schema_versions


def test_initialize_creates_the_complete_application_schema() -> None:
    database = Database("sqlite+pysqlite:///:memory:")

    database.initialize()

    tables = set(inspect(database.engine).get_table_names())
    assert {
        "schema_versions",
        "system_settings",
        "users",
        "records",
        "integration_settings",
        "audit_logs",
        "materials",
        "material_chunks",
    } <= tables
    with database.session() as session:
        assert session.scalar(select(schema_versions.c.version)) == SCHEMA_VERSION


def test_initialize_migrates_v1_material_metadata_without_losing_rows(tmp_path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'v1.sqlite3').as_posix()}")
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE schema_versions ("
                "version INTEGER PRIMARY KEY, applied_at DATETIME NOT NULL)"
            )
        )
        connection.execute(text("INSERT INTO schema_versions VALUES (1, CURRENT_TIMESTAMP)"))
        connection.execute(
            text("""
            CREATE TABLE materials (
                owner_id VARCHAR(128) NOT NULL,
                project_id VARCHAR(128) NOT NULL,
                material_id VARCHAR(128) NOT NULL,
                filename VARCHAR(500) NOT NULL,
                content_type VARCHAR(200) NOT NULL,
                size BIGINT NOT NULL,
                status VARCHAR(32) NOT NULL,
                chunk_count INTEGER NOT NULL,
                content_sha256 VARCHAR(64) NOT NULL,
                storage_key VARCHAR(1000),
                indexed_at DATETIME NOT NULL,
                UNIQUE (owner_id, project_id, material_id)
            )
        """)
        )
        connection.execute(
            text("""
            INSERT INTO materials VALUES (
                'owner', 'workspace', 'material-1', 'limits.txt', 'text/plain',
                12, 'indexed', 1, 'abc', 'objects/limits', CURRENT_TIMESTAMP
            )
        """)
        )

    database.initialize()

    columns = {column["name"] for column in inspect(database.engine).get_columns("materials")}
    assert {"title", "tags"} <= columns
    with database.engine.connect() as connection:
        row = connection.execute(
            text("SELECT filename, title, tags FROM materials WHERE material_id = 'material-1'")
        ).one()
        assert row.filename == "limits.txt"
        assert row.title == "limits.txt"
        assert row.tags == "[]"
        assert connection.scalar(text("SELECT version FROM schema_versions")) == SCHEMA_VERSION


def test_database_health_check_executes_a_real_query() -> None:
    database = Database("sqlite+pysqlite:///:memory:")
    database.initialize()

    assert database.ping() is True
    assert database.is_postgresql is False
