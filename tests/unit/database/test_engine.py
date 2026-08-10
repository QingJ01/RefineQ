"""Database engine and schema lifecycle tests."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from refineq.database.engine import Database
from refineq.database.schema import (
    SCHEMA_VERSION,
    material_chunks,
    materials,
    schema_versions,
    workspace_materials,
)


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
        "workspace_materials",
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
            text(
                "SELECT filename, title, tags, project_id FROM materials "
                "WHERE material_id = 'material-1'"
            )
        ).one()
        assert row.filename == "limits.txt"
        assert row.title == "limits.txt"
        assert row.tags == "[]"
        assert row.project_id == "library"
        assert (
            connection.scalar(
                text(
                    "SELECT COUNT(*) FROM workspace_materials "
                    "WHERE owner_id = 'owner' AND workspace_id = 'workspace' "
                    "AND material_id = 'material-1'"
                )
            )
            == 1
        )
        assert connection.scalar(text("SELECT version FROM schema_versions")) == SCHEMA_VERSION


def test_database_health_check_executes_a_real_query() -> None:
    database = Database("sqlite+pysqlite:///:memory:")
    database.initialize()

    assert database.ping() is True
    assert database.is_postgresql is False


def test_v2_migration_deduplicates_identical_materials_across_workspaces(tmp_path) -> None:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'v2-duplicates.sqlite3').as_posix()}")
    database.initialize()
    with database.engine.begin() as connection:
        connection.execute(text("DROP INDEX uq_materials_owner_material"))
        connection.execute(text("DELETE FROM workspace_materials"))
        connection.execute(text("UPDATE schema_versions SET version = 2"))
        for workspace_id in ("calculus", "linear-algebra"):
            connection.execute(
                materials.insert().values(
                    owner_id="owner",
                    project_id=workspace_id,
                    material_id="same-content",
                    filename=f"{workspace_id}.txt",
                    title=f"{workspace_id} notes",
                    tags=[],
                    content_type="text/plain",
                    size=12,
                    status="indexed",
                    chunk_count=1,
                    content_sha256="a" * 64,
                    storage_key=f"objects/{workspace_id}/same-content.txt",
                )
            )
            connection.execute(
                material_chunks.insert().values(
                    owner_id="owner",
                    project_id=workspace_id,
                    material_id="same-content",
                    filename=f"{workspace_id}.txt",
                    chunk_index=0,
                    content="shared mathematical content",
                    embedding=None,
                )
            )

    database.initialize()

    with database.engine.connect() as connection:
        material_rows = connection.execute(
            select(materials).where(materials.c.owner_id == "owner")
        ).all()
        chunk_rows = connection.execute(
            select(material_chunks).where(material_chunks.c.owner_id == "owner")
        ).all()
        link_rows = connection.execute(
            select(workspace_materials).where(workspace_materials.c.owner_id == "owner")
        ).all()
    assert len(material_rows) == 1
    assert material_rows[0].project_id == "library"
    assert len(chunk_rows) == 1
    assert chunk_rows[0].project_id == "library"
    assert {(row.workspace_id, row.material_id) for row in link_rows} == {
        ("calculus", "same-content"),
        ("linear-algebra", "same-content"),
    }

    with pytest.raises(IntegrityError), database.engine.begin() as connection:
        connection.execute(
            materials.insert().values(
                owner_id="owner",
                project_id="legacy-workspace",
                material_id="same-content",
                filename="duplicate.txt",
                title="duplicate",
                tags=[],
                content_type="text/plain",
                size=1,
                status="indexed",
                chunk_count=0,
                content_sha256="b" * 64,
                storage_key="objects/duplicate.txt",
            )
        )
