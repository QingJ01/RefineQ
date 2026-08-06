"""Owner-local SQLite FTS5 index for study-material chunks."""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Lock, RLock

from pydantic import BaseModel, ConfigDict, Field

from refineq.storage.json_store import validate_identifier


class MaterialRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    project_id: str
    filename: str
    content_type: str
    size: int = Field(ge=0)
    status: str
    chunk_count: int = Field(ge=0)
    content_sha256: str
    indexed_at: datetime


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: str
    material_id: str
    filename: str
    chunk_index: int
    text: str
    score: float


class MaterialNotFoundError(LookupError):
    """Raised when an indexed material is outside the requested scope."""


class KnowledgeIndex:
    _locks_guard = Lock()
    _locks: dict[str, RLock] = {}

    def __init__(self, data_root: Path, *, chunk_chars: int = 1_200) -> None:
        self.data_root = data_root.expanduser().resolve()
        self.chunk_chars = chunk_chars

    @classmethod
    def _lock_for(cls, path: Path) -> RLock:
        key = os.path.normcase(str(path))
        with cls._locks_guard:
            return cls._locks.setdefault(key, RLock())

    def _database_path(self, owner_id: str) -> Path:
        owner_id = validate_identifier(owner_id, field="owner_id")
        return self.data_root / "users" / owner_id / "knowledge" / "search.sqlite3"

    @staticmethod
    def _connect(path: Path) -> sqlite3.Connection:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS materials (
                project_id TEXT NOT NULL,
                material_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                content_type TEXT NOT NULL,
                size INTEGER NOT NULL,
                status TEXT NOT NULL,
                chunk_count INTEGER NOT NULL,
                content_sha256 TEXT NOT NULL,
                indexed_at TEXT NOT NULL,
                PRIMARY KEY (project_id, material_id)
            )
            """
        )
        connection.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS material_chunks USING fts5(
                project_id UNINDEXED,
                material_id UNINDEXED,
                filename UNINDEXED,
                chunk_index UNINDEXED,
                content,
                tokenize='unicode61'
            )
            """
        )
        return connection

    def _chunks(self, text: str) -> list[str]:
        paragraphs = [paragraph.strip() for paragraph in text.split("\n") if paragraph.strip()]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if current and len(current) + len(paragraph) + 1 > self.chunk_chars:
                chunks.append(current)
                current = ""
            while len(paragraph) > self.chunk_chars:
                chunks.append(paragraph[: self.chunk_chars])
                paragraph = paragraph[self.chunk_chars :]
            current = f"{current}\n{paragraph}".strip()
        if current:
            chunks.append(current)
        return chunks

    def add_document(
        self,
        *,
        owner_id: str,
        project_id: str,
        material_id: str,
        filename: str,
        text: str,
        content_type: str = "text/plain",
        size: int | None = None,
    ) -> MaterialRecord:
        project_id = validate_identifier(project_id, field="project_id")
        material_id = validate_identifier(material_id, field="material_id")
        chunks = self._chunks(text)
        if not chunks:
            raise ValueError("Indexed text must not be blank")
        indexed_at = datetime.now(UTC)
        encoded = text.encode("utf-8")
        record = MaterialRecord(
            id=material_id,
            project_id=project_id,
            filename=filename,
            content_type=content_type,
            size=len(encoded) if size is None else size,
            status="indexed",
            chunk_count=len(chunks),
            content_sha256=sha256(encoded).hexdigest(),
            indexed_at=indexed_at,
        )
        path = self._database_path(owner_id)
        with self._lock_for(path), self._connect(path) as connection:
            connection.execute(
                "DELETE FROM material_chunks WHERE project_id = ? AND material_id = ?",
                (project_id, material_id),
            )
            connection.execute(
                "DELETE FROM materials WHERE project_id = ? AND material_id = ?",
                (project_id, material_id),
            )
            connection.execute(
                """
                INSERT INTO materials VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    material_id,
                    filename,
                    content_type,
                    record.size,
                    record.status,
                    record.chunk_count,
                    record.content_sha256,
                    indexed_at.isoformat(),
                ),
            )
            connection.executemany(
                "INSERT INTO material_chunks VALUES (?, ?, ?, ?, ?)",
                [
                    (project_id, material_id, filename, index, chunk)
                    for index, chunk in enumerate(chunks)
                ],
            )
        return record

    @staticmethod
    def _match_query(query: str) -> str:
        tokens = re.findall(r"\w+", query, flags=re.UNICODE)
        if not tokens:
            raise ValueError("Search query must contain a word")
        return " OR ".join(f'"{token}"' for token in tokens[:20])

    def search(
        self,
        *,
        owner_id: str,
        project_id: str,
        query: str,
        limit: int = 8,
    ) -> list[SearchResult]:
        project_id = validate_identifier(project_id, field="project_id")
        path = self._database_path(owner_id)
        if not path.exists():
            return []
        match_query = self._match_query(query)
        with self._lock_for(path), self._connect(path) as connection:
            rows = connection.execute(
                """
                SELECT material_id, filename, chunk_index, content, bm25(material_chunks) AS rank
                FROM material_chunks
                WHERE material_chunks MATCH ? AND project_id = ?
                ORDER BY rank, material_id, CAST(chunk_index AS INTEGER)
                LIMIT ?
                """,
                (match_query, project_id, max(1, min(limit, 50))),
            ).fetchall()
        return [
            SearchResult(
                citation_id=f"{row['material_id']}#{row['chunk_index']}",
                material_id=row["material_id"],
                filename=row["filename"],
                chunk_index=int(row["chunk_index"]),
                text=row["content"],
                score=float(-row["rank"]),
            )
            for row in rows
        ]

    def get_material(
        self,
        *,
        owner_id: str,
        project_id: str,
        material_id: str,
    ) -> MaterialRecord:
        project_id = validate_identifier(project_id, field="project_id")
        material_id = validate_identifier(material_id, field="material_id")
        path = self._database_path(owner_id)
        if not path.exists():
            raise MaterialNotFoundError(material_id)
        with self._lock_for(path), self._connect(path) as connection:
            row = connection.execute(
                "SELECT * FROM materials WHERE project_id = ? AND material_id = ?",
                (project_id, material_id),
            ).fetchone()
        if row is None:
            raise MaterialNotFoundError(material_id)
        return MaterialRecord(
            id=row["material_id"],
            project_id=row["project_id"],
            filename=row["filename"],
            content_type=row["content_type"],
            size=row["size"],
            status=row["status"],
            chunk_count=row["chunk_count"],
            content_sha256=row["content_sha256"],
            indexed_at=datetime.fromisoformat(row["indexed_at"]),
        )
