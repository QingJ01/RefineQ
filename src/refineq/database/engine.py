"""Engine lifecycle and transaction boundaries."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, and_, create_engine, delete, insert, inspect, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from refineq.database.schema import SCHEMA_VERSION, metadata, schema_versions


class Database:
    """Own one SQLAlchemy engine and initialize the application schema."""

    def __init__(self, url: str) -> None:
        parsed = make_url(url)
        if parsed.drivername not in {"postgresql+psycopg", "sqlite+pysqlite"}:
            raise ValueError("database URL must use PostgreSQL or SQLite")
        self.url = url
        self.is_postgresql = parsed.get_backend_name() == "postgresql"

        options: dict[str, object] = {"pool_pre_ping": True}
        if parsed.get_backend_name() == "sqlite":
            if parsed.database and parsed.database != ":memory:":
                database_parent = Path(parsed.database).expanduser().resolve().parent
                database_parent.mkdir(parents=True, exist_ok=True)
            options["connect_args"] = {"check_same_thread": False}
            if parsed.database in {None, "", ":memory:"}:
                options["poolclass"] = StaticPool

        self.engine: Engine = create_engine(url, **options)
        self._session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    def initialize(self) -> None:
        """Create extensions and tables, then record the current schema version."""

        with self.engine.begin() as connection:
            if self.is_postgresql:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
            metadata.create_all(connection)
            if not self.is_postgresql:
                connection.execute(
                    text("UPDATE material_chunks SET embedding = NULL WHERE embedding = 'null'")
                )
            current = connection.scalar(select(schema_versions.c.version).limit(1))
            if current is None:
                connection.execute(insert(schema_versions).values(version=SCHEMA_VERSION))
                current_version = SCHEMA_VERSION
            else:
                current_version = int(current)
            if current_version == 1:
                user_columns = {
                    column["name"] for column in inspect(connection).get_columns("users")
                }
                material_columns = {
                    column["name"] for column in inspect(connection).get_columns("materials")
                }
                if "deletion_id" not in user_columns:
                    connection.execute(text("ALTER TABLE users ADD COLUMN deletion_id VARCHAR(64)"))
                if self.is_postgresql:
                    if "title" not in material_columns:
                        connection.execute(
                            text("ALTER TABLE materials ADD COLUMN title VARCHAR(500)")
                        )
                    if "tags" not in material_columns:
                        connection.execute(
                            text(
                                "ALTER TABLE materials ADD COLUMN tags JSONB "
                                "NOT NULL DEFAULT '[]'::jsonb"
                            )
                        )
                    connection.execute(text("UPDATE materials SET title = filename"))
                    connection.execute(
                        text("ALTER TABLE materials ALTER COLUMN title SET NOT NULL")
                    )
                else:
                    if "title" not in material_columns:
                        connection.execute(
                            text("ALTER TABLE materials ADD COLUMN title VARCHAR(500)")
                        )
                    if "tags" not in material_columns:
                        connection.execute(
                            text("ALTER TABLE materials ADD COLUMN tags JSON NOT NULL DEFAULT '[]'")
                        )
                    connection.execute(text("UPDATE materials SET title = filename"))
                connection.execute(
                    text("UPDATE schema_versions SET version = :version"),
                    {"version": 2},
                )
                current_version = 2
            if current_version == 2:
                connection.execute(
                    text(
                        "INSERT INTO workspace_materials "
                        "(owner_id, workspace_id, material_id, added_at) "
                        "SELECT owner_id, project_id, material_id, indexed_at FROM materials "
                        "WHERE project_id <> 'library'"
                    )
                )
                legacy_rows = connection.execute(
                    select(
                        metadata.tables["materials"].c.owner_id,
                        metadata.tables["materials"].c.material_id,
                        metadata.tables["materials"].c.project_id,
                        metadata.tables["materials"].c.status,
                        metadata.tables["materials"].c.chunk_count,
                        metadata.tables["materials"].c.indexed_at,
                    ).order_by(
                        metadata.tables["materials"].c.owner_id,
                        metadata.tables["materials"].c.material_id,
                        metadata.tables["materials"].c.project_id,
                    )
                ).all()
                material_table = metadata.tables["materials"]
                chunk_table = metadata.tables["material_chunks"]
                grouped_rows: dict[tuple[str, str], list[object]] = {}
                for row in legacy_rows:
                    grouped_rows.setdefault((str(row.owner_id), str(row.material_id)), []).append(
                        row
                    )
                for (owner_id, material_id), candidate_rows in grouped_rows.items():
                    source = max(
                        candidate_rows,
                        key=lambda row: (
                            str(row.status) == "indexed",
                            int(row.chunk_count),
                            row.indexed_at,
                            str(row.project_id) == "library",
                            str(row.project_id),
                        ),
                    )
                    source_project = str(source.project_id)
                    duplicate_projects = [
                        str(row.project_id)
                        for row in candidate_rows
                        if str(row.project_id) != source_project
                    ]
                    if duplicate_projects:
                        connection.execute(
                            delete(chunk_table).where(
                                chunk_table.c.owner_id == owner_id,
                                chunk_table.c.material_id == material_id,
                                chunk_table.c.project_id.in_(duplicate_projects),
                            )
                        )
                        connection.execute(
                            delete(material_table).where(
                                material_table.c.owner_id == owner_id,
                                material_table.c.material_id == material_id,
                                material_table.c.project_id.in_(duplicate_projects),
                            )
                        )
                    if source_project != "library":
                        scope = and_(
                            material_table.c.owner_id == owner_id,
                            material_table.c.material_id == material_id,
                            material_table.c.project_id == source_project,
                        )
                        connection.execute(
                            update(material_table).where(scope).values(project_id="library")
                        )
                        connection.execute(
                            update(chunk_table)
                            .where(
                                chunk_table.c.owner_id == owner_id,
                                chunk_table.c.material_id == material_id,
                                chunk_table.c.project_id == source_project,
                            )
                            .values(project_id="library")
                        )
                connection.execute(
                    text("UPDATE schema_versions SET version = :version"),
                    {"version": 3},
                )
                current_version = 3
            if current_version == 3:
                connection.execute(
                    text("UPDATE schema_versions SET version = :version"),
                    {"version": 4},
                )
                current_version = 4
            if current_version == 4:
                run_columns = {
                    column["name"]
                    for column in inspect(connection).get_columns("mcp_evaluation_runs")
                }
                if "generation" not in run_columns:
                    connection.execute(
                        text(
                            "ALTER TABLE mcp_evaluation_runs ADD COLUMN generation "
                            "VARCHAR(32) NOT NULL DEFAULT 'legacy'"
                        )
                    )
                connection.execute(
                    text("UPDATE schema_versions SET version = :version"),
                    {"version": 5},
                )
                current_version = 5
            if current_version != SCHEMA_VERSION:
                raise RuntimeError(
                    f"Unsupported database schema {current_version}; expected {SCHEMA_VERSION}"
                )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_materials_owner_material "
                    "ON materials (owner_id, material_id)"
                )
            )
            if self.is_postgresql:
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_material_chunks_content_fts "
                        "ON material_chunks USING gin (to_tsvector('simple', content))"
                    )
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_material_chunks_content_trgm "
                        "ON material_chunks USING gin (content gin_trgm_ops)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_material_chunks_embedding_hnsw "
                        "ON material_chunks USING hnsw (embedding vector_cosine_ops) "
                        "WHERE embedding IS NOT NULL"
                    )
                )

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Commit on success and always roll back failed transactions."""

        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def ping(self) -> bool:
        with self.engine.connect() as connection:
            return connection.scalar(text("SELECT 1")) == 1

    def close(self) -> None:
        self.engine.dispose()
