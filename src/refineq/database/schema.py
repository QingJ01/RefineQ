"""Shared SQL schema for durable RefineQ state."""

from __future__ import annotations

from datetime import UTC, datetime

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB

SCHEMA_VERSION = 1
EMBEDDING_DIMENSIONS = 1536

naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=naming_convention)

json_document = JSON().with_variant(JSONB(), "postgresql")
embedding_vector = JSON(none_as_null=True).with_variant(
    VECTOR(EMBEDDING_DIMENSIONS),
    "postgresql",
)


def utc_now() -> datetime:
    return datetime.now(UTC)


schema_versions = Table(
    "schema_versions",
    metadata,
    Column("version", Integer, primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

system_settings = Table(
    "system_settings",
    metadata,
    Column("key", String(100), primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
)

users = Table(
    "users",
    metadata,
    Column("id", String(128), primary_key=True),
    Column("email", String(254), nullable=False, unique=True),
    Column("display_name", String(100), nullable=False),
    Column("password_hash", String(128), nullable=False),
    Column("role", String(20), nullable=False, default="learner"),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    CheckConstraint("role IN ('learner', 'admin')", name="valid_role"),
)

records = Table(
    "records",
    metadata,
    Column("owner_id", String(128), nullable=False),
    Column("collection", String(128), nullable=False),
    Column("record_id", String(128), nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("version", Integer, nullable=False),
    Column("data", json_document, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    UniqueConstraint("owner_id", "collection", "record_id"),
    CheckConstraint("schema_version > 0", name="positive_schema_version"),
    CheckConstraint("version > 0", name="positive_version"),
)
Index("ix_records_owner_collection", records.c.owner_id, records.c.collection)

integration_settings = Table(
    "integration_settings",
    metadata,
    Column("kind", String(32), primary_key=True),
    Column("enabled", Boolean, nullable=False, default=False),
    Column("config", json_document, nullable=False, default=dict),
    Column("encrypted_secrets", Text, nullable=False, default=""),
    Column("updated_by", String(128), ForeignKey("users.id"), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=utc_now),
    Column("last_test_status", String(32), nullable=True),
    Column("last_test_message", String(500), nullable=True),
    Column("last_tested_at", DateTime(timezone=True), nullable=True),
)

audit_logs = Table(
    "audit_logs",
    metadata,
    Column(
        "id",
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    ),
    Column("actor_id", String(128), ForeignKey("users.id"), nullable=False),
    Column("action", String(100), nullable=False),
    Column("target", String(128), nullable=False),
    Column("details", json_document, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), nullable=False, default=utc_now),
)
Index("ix_audit_logs_created_at", audit_logs.c.created_at)

materials = Table(
    "materials",
    metadata,
    Column("owner_id", String(128), nullable=False),
    Column("project_id", String(128), nullable=False),
    Column("material_id", String(128), nullable=False),
    Column("filename", String(500), nullable=False),
    Column("content_type", String(200), nullable=False),
    Column("size", BigInteger, nullable=False),
    Column("status", String(32), nullable=False),
    Column("chunk_count", Integer, nullable=False),
    Column("content_sha256", String(64), nullable=False),
    Column("storage_key", String(1000), nullable=True),
    Column("indexed_at", DateTime(timezone=True), nullable=False, default=utc_now),
    UniqueConstraint("owner_id", "project_id", "material_id"),
    CheckConstraint("size >= 0", name="non_negative_size"),
    CheckConstraint("chunk_count >= 0", name="non_negative_chunk_count"),
)
Index("ix_materials_owner_project", materials.c.owner_id, materials.c.project_id)

material_chunks = Table(
    "material_chunks",
    metadata,
    Column("owner_id", String(128), nullable=False),
    Column("project_id", String(128), nullable=False),
    Column("material_id", String(128), nullable=False),
    Column("filename", String(500), nullable=False),
    Column("chunk_index", Integer, nullable=False),
    Column("content", Text, nullable=False),
    Column("embedding", embedding_vector, nullable=True),
    UniqueConstraint("owner_id", "project_id", "material_id", "chunk_index"),
    CheckConstraint("chunk_index >= 0", name="non_negative_chunk_index"),
)
Index(
    "ix_material_chunks_owner_project",
    material_chunks.c.owner_id,
    material_chunks.c.project_id,
)


ALL_TABLES = (
    schema_versions,
    system_settings,
    users,
    records,
    integration_settings,
    audit_logs,
    materials,
    material_chunks,
)
