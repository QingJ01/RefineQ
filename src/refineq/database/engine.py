"""Engine lifecycle and transaction boundaries."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, insert, inspect, select, text
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
                connection.execute(
                    text(
                        "UPDATE material_chunks SET project_id = 'library' "
                        "WHERE project_id <> 'library'"
                    )
                )
                connection.execute(
                    text(
                        "UPDATE materials SET project_id = 'library' "
                        "WHERE project_id <> 'library'"
                    )
                )
                connection.execute(
                    text("UPDATE schema_versions SET version = :version"),
                    {"version": 3},
                )
                current_version = 3
            if current_version != SCHEMA_VERSION:
                raise RuntimeError(
                    f"Unsupported database schema {current_version}; expected {SCHEMA_VERSION}"
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
