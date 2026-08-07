"""PostgreSQL full-text and pgvector-backed study material index."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Lock, RLock

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, insert, select

from refineq.database.engine import Database
from refineq.database.schema import material_chunks, materials
from refineq.knowledge.embeddings import Embedder
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


@dataclass(frozen=True, slots=True)
class MaterialDocument:
    project_id: str
    material_id: str
    filename: str
    text: str
    content_type: str = "text/plain"
    size: int | None = None
    storage_key: str | None = None


class KnowledgeIndex:
    """Store chunks in SQL and combine lexical and semantic relevance."""

    _locks_guard = Lock()
    _locks: dict[str, RLock] = {}

    def __init__(
        self,
        database: Database | Path,
        *,
        chunk_chars: int = 1_200,
        embedder: Embedder | None = None,
    ) -> None:
        if isinstance(database, Path):
            path = database.expanduser().resolve() / "system" / "refineq.sqlite3"
            database = Database(f"sqlite+pysqlite:///{path.as_posix()}")
            database.initialize()
        self.database = database
        self.chunk_chars = chunk_chars
        self.embedder = embedder

    @classmethod
    def _lock_for(cls, key: str) -> RLock:
        with cls._locks_guard:
            return cls._locks.setdefault(key, RLock())

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

    def _embed_or_none(self, texts: list[str]) -> list[list[float] | None]:
        if self.embedder is None:
            return [None] * len(texts)
        try:
            vectors = self.embedder.embed(texts)
            if len(vectors) != len(texts):
                raise ValueError("Embedding count does not match chunk count")
            return vectors
        except Exception:
            return [None] * len(texts)

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @classmethod
    def _material_record(cls, row) -> MaterialRecord:
        return MaterialRecord(
            id=row.material_id,
            project_id=row.project_id,
            filename=row.filename,
            content_type=row.content_type,
            size=int(row.size),
            status=row.status,
            chunk_count=int(row.chunk_count),
            content_sha256=row.content_sha256,
            indexed_at=cls._aware(row.indexed_at),
        )

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
        storage_key: str | None = None,
    ) -> MaterialRecord:
        return self.add_documents(
            owner_id=owner_id,
            documents=[
                MaterialDocument(
                    project_id=project_id,
                    material_id=material_id,
                    filename=filename,
                    text=text,
                    content_type=content_type,
                    size=size,
                    storage_key=storage_key,
                )
            ],
        )[0]

    def add_documents(
        self,
        *,
        owner_id: str,
        documents: list[MaterialDocument],
    ) -> list[MaterialRecord]:
        if not documents:
            raise ValueError("At least one indexed document is required")
        owner_id = validate_identifier(owner_id, field="owner_id")
        prepared: list[tuple[MaterialRecord, MaterialDocument, list[str]]] = []
        seen: set[tuple[str, str]] = set()
        indexed_at = datetime.now(UTC)
        for document in documents:
            project_id = validate_identifier(document.project_id, field="project_id")
            material_id = validate_identifier(document.material_id, field="material_id")
            identity = (project_id, material_id)
            if identity in seen:
                raise ValueError("Material IDs must be unique within a batch")
            seen.add(identity)
            chunks = self._chunks(document.text)
            if not chunks:
                raise ValueError("Indexed text must not be blank")
            encoded = document.text.encode("utf-8")
            record = MaterialRecord(
                id=material_id,
                project_id=project_id,
                filename=document.filename,
                content_type=document.content_type,
                size=len(encoded) if document.size is None else document.size,
                status="indexed",
                chunk_count=len(chunks),
                content_sha256=sha256(encoded).hexdigest(),
                indexed_at=indexed_at,
            )
            prepared.append((record, document, chunks))

        all_chunks = [chunk for _, _, chunks in prepared for chunk in chunks]
        embeddings = iter(self._embed_or_none(all_chunks))
        with self._lock_for(owner_id), self.database.session() as session:
            for record, document, chunks in prepared:
                scope = (
                    materials.c.owner_id == owner_id,
                    materials.c.project_id == record.project_id,
                    materials.c.material_id == record.id,
                )
                session.execute(
                    delete(material_chunks).where(
                        material_chunks.c.owner_id == owner_id,
                        material_chunks.c.project_id == record.project_id,
                        material_chunks.c.material_id == record.id,
                    )
                )
                session.execute(delete(materials).where(*scope))
                session.execute(
                    insert(materials).values(
                        owner_id=owner_id,
                        project_id=record.project_id,
                        material_id=record.id,
                        filename=record.filename,
                        content_type=record.content_type,
                        size=record.size,
                        status=record.status,
                        chunk_count=record.chunk_count,
                        content_sha256=record.content_sha256,
                        storage_key=document.storage_key,
                        indexed_at=record.indexed_at,
                    )
                )
                session.execute(
                    insert(material_chunks),
                    [
                        {
                            "owner_id": owner_id,
                            "project_id": record.project_id,
                            "material_id": record.id,
                            "filename": record.filename,
                            "chunk_index": index,
                            "content": chunk,
                            "embedding": next(embeddings),
                        }
                        for index, chunk in enumerate(chunks)
                    ],
                )
        return [record for record, _, _ in prepared]

    def owner_material_usage(self, *, owner_id: str) -> tuple[int, int]:
        owner_id = validate_identifier(owner_id, field="owner_id")
        with self.database.session() as session:
            row = session.execute(
                select(func.count(), func.coalesce(func.sum(materials.c.size), 0)).where(
                    materials.c.owner_id == owner_id
                )
            ).one()
        return int(row[0]), int(row[1])

    @staticmethod
    def _lexical_score(content: str, query: str) -> float:
        content_lower = content.casefold()
        query_lower = query.strip().casefold()
        if not query_lower:
            raise ValueError("Search query must contain a word")
        tokens = re.findall(r"\w+", query_lower, flags=re.UNICODE)
        if not tokens:
            raise ValueError("Search query must contain a word")
        score = sum(content_lower.count(token) for token in tokens[:20])
        if query_lower in content_lower:
            score += 2
        return float(score)

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        dot = sum(a * b for a, b in zip(left, right, strict=True))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return max(-1.0, min(1.0, dot / (left_norm * right_norm)))

    def _query_embedding(self, query: str) -> list[float] | None:
        if self.embedder is None:
            return None
        try:
            vectors = self.embedder.embed([query])
            return vectors[0] if len(vectors) == 1 else None
        except Exception:
            return None

    def search(
        self,
        *,
        owner_id: str,
        project_id: str,
        query: str,
        limit: int = 8,
    ) -> list[SearchResult]:
        owner_id = validate_identifier(owner_id, field="owner_id")
        project_id = validate_identifier(project_id, field="project_id")
        query_embedding = self._query_embedding(query)
        with self.database.session() as session:
            rows = session.execute(
                select(material_chunks).where(
                    material_chunks.c.owner_id == owner_id,
                    material_chunks.c.project_id == project_id,
                )
            ).all()

            database_scores: dict[tuple[str, int], float] = {}
            if self.database.is_postgresql and query_embedding is not None:
                distance = material_chunks.c.embedding.cosine_distance(query_embedding)
                semantic_rows = session.execute(
                    select(
                        material_chunks.c.material_id,
                        material_chunks.c.chunk_index,
                        (1 - distance).label("semantic_score"),
                    )
                    .where(
                        material_chunks.c.owner_id == owner_id,
                        material_chunks.c.project_id == project_id,
                        material_chunks.c.embedding.is_not(None),
                    )
                    .order_by(distance)
                    .limit(max(50, limit * 8))
                ).all()
                database_scores = {
                    (row.material_id, int(row.chunk_index)): float(row.semantic_score)
                    for row in semantic_rows
                }

        scored: list[tuple[float, object]] = []
        lexical_scores = [self._lexical_score(row.content, query) for row in rows]
        lexical_max = max(lexical_scores, default=0.0)
        for row, lexical in zip(rows, lexical_scores, strict=True):
            semantic = database_scores.get((row.material_id, int(row.chunk_index)), 0.0)
            if (
                not self.database.is_postgresql
                and query_embedding is not None
                and row.embedding is not None
            ):
                semantic = self._cosine(list(row.embedding), query_embedding)
            if query_embedding is None and lexical <= 0:
                continue
            normalized_lexical = lexical / lexical_max if lexical_max else 0.0
            score = (
                normalized_lexical
                if query_embedding is None
                else 0.35 * normalized_lexical + 0.65 * max(0.0, semantic)
            )
            if score > 0:
                scored.append((score, row))

        scored.sort(key=lambda item: (-item[0], item[1].material_id, item[1].chunk_index))
        return [
            SearchResult(
                citation_id=f"{row.material_id}#{row.chunk_index}",
                material_id=row.material_id,
                filename=row.filename,
                chunk_index=int(row.chunk_index),
                text=row.content,
                score=float(score),
            )
            for score, row in scored[: max(1, min(limit, 50))]
        ]

    def get_material(
        self,
        *,
        owner_id: str,
        project_id: str,
        material_id: str,
    ) -> MaterialRecord:
        owner_id = validate_identifier(owner_id, field="owner_id")
        project_id = validate_identifier(project_id, field="project_id")
        material_id = validate_identifier(material_id, field="material_id")
        with self.database.session() as session:
            row = session.execute(
                select(materials).where(
                    materials.c.owner_id == owner_id,
                    materials.c.project_id == project_id,
                    materials.c.material_id == material_id,
                )
            ).one_or_none()
        if row is None:
            raise MaterialNotFoundError(material_id)
        return self._material_record(row)

    def list_materials(
        self,
        *,
        owner_id: str,
        project_id: str,
    ) -> list[MaterialRecord]:
        owner_id = validate_identifier(owner_id, field="owner_id")
        project_id = validate_identifier(project_id, field="project_id")
        with self.database.session() as session:
            rows = session.execute(
                select(materials)
                .where(
                    materials.c.owner_id == owner_id,
                    materials.c.project_id == project_id,
                )
                .order_by(materials.c.indexed_at.desc(), materials.c.material_id)
            ).all()
        return [self._material_record(row) for row in rows]
