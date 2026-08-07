"""Database engine and schema lifecycle tests."""

from __future__ import annotations

from sqlalchemy import inspect, select

from refineq.database.engine import Database
from refineq.database.schema import schema_versions


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
        assert session.scalar(select(schema_versions.c.version)) == 1


def test_database_health_check_executes_a_real_query() -> None:
    database = Database("sqlite+pysqlite:///:memory:")
    database.initialize()

    assert database.ping() is True
    assert database.is_postgresql is False
