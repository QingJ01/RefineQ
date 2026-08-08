"""PostgreSQL full-text and pgvector-backed study material index."""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Lock, RLock

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    and_,
    case,
    delete,
    func,
    insert,
    literal_column,
    or_,
    select,
    type_coerce,
    update,
)
from sqlalchemy import (
    text as sql_text,
)

from refineq.database.engine import Database
from refineq.database.owner_state import lock_writable_owner
from refineq.database.schema import EMBEDDING_DIMENSIONS, material_chunks, materials
from refineq.knowledge.embeddings import Embedder
from refineq.storage.json_store import validate_identifier

logger = logging.getLogger(__name__)


def _lexical_terms(query: str) -> list[str]:
    """Return bounded search terms, including bigrams for unsegmented CJK text."""

    segments = re.findall(
        r"[\u3400-\u4dbf\u4e00-\u9fff]+|[^\W_]+",
        query.casefold(),
        flags=re.UNICODE,
    )
    terms: list[str] = []
    for segment in segments:
        if re.fullmatch(r"[\u3400-\u4dbf\u4e00-\u9fff]+", segment):
            terms.extend(segment[index : index + 2] for index in range(max(1, len(segment) - 1)))
        else:
            terms.append(segment)
    return list(dict.fromkeys(term for term in terms if term))[:20]


def _postgres_cosine_distance(column: object, query_embedding: list[float]):
    """Apply pgvector operators when shared metadata uses a SQLite JSON fallback."""

    from pgvector.sqlalchemy import VECTOR

    vector_column = type_coerce(column, VECTOR(EMBEDDING_DIMENSIONS))
    return vector_column.cosine_distance(query_embedding)


class MaterialRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    project_id: str
    filename: str
    title: str
    tags: list[str]
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


class MaterialQuotaExceededError(ValueError):
    """Raised when a material transaction would exceed its owner's quota."""


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
        embedding_batch_size: int = 64,
        enforce_owner_state: bool = False,
    ) -> None:
        if isinstance(database, Path):
            path = database.expanduser().resolve() / "system" / "refineq.sqlite3"
            database = Database(f"sqlite+pysqlite:///{path.as_posix()}")
            database.initialize()
        self.database = database
        self.chunk_chars = chunk_chars
        self.embedder = embedder
        if embedding_batch_size < 1:
            raise ValueError("embedding_batch_size must be positive")
        self.embedding_batch_size = embedding_batch_size
        self.enforce_owner_state = enforce_owner_state

    def _lock_owner_write(self, session, owner_id: str) -> None:
        if self.enforce_owner_state:
            lock_writable_owner(session, self.database, owner_id)

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
        embedded: list[list[float] | None] = []
        for start in range(0, len(texts), self.embedding_batch_size):
            batch = texts[start : start + self.embedding_batch_size]
            try:
                vectors = self.embedder.embed(batch)
                if len(vectors) != len(batch):
                    raise ValueError("Embedding count does not match chunk count")
                embedded.extend(vectors)
            except Exception as error:
                logger.warning(
                    "Embedding batch failed; lexical retrieval remains available (%s)",
                    type(error).__name__,
                )
                embedded.extend([None] * len(batch))
        return embedded

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
            title=row.title or row.filename,
            tags=list(row.tags or []),
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
        owner_id, prepared = self._prepare_documents(owner_id=owner_id, documents=documents)
        embeddings = self._embed_prepared(prepared)
        with self._lock_for(owner_id), self.database.session() as session:
            self._lock_owner_write(session, owner_id)
            self._write_prepared(
                session=session,
                owner_id=owner_id,
                prepared=prepared,
                embeddings=embeddings,
            )
        return [record for record, _, _ in prepared]

    def add_documents_with_quota(
        self,
        *,
        owner_id: str,
        documents: list[MaterialDocument],
        max_count: int,
        max_bytes: int,
    ) -> list[MaterialRecord]:
        """Validate quota and replace documents inside one owner-serialized transaction."""

        if max_count < 1 or max_bytes < 1:
            raise ValueError("Material quotas must be positive")
        owner_id, prepared = self._prepare_documents(owner_id=owner_id, documents=documents)
        embeddings = self._embed_prepared(prepared)
        with self._lock_for(owner_id), self.database.session() as session:
            self._lock_owner_write(session, owner_id)
            if self.database.is_postgresql:
                session.execute(
                    sql_text("SELECT pg_advisory_xact_lock(hashtextextended(:owner_id, 0))"),
                    {"owner_id": owner_id},
                )
            total_count, total_bytes = session.execute(
                select(func.count(), func.coalesce(func.sum(materials.c.size), 0)).where(
                    materials.c.owner_id == owner_id
                )
            ).one()
            identities = [
                and_(
                    materials.c.project_id == record.project_id,
                    materials.c.material_id == record.id,
                )
                for record, _, _ in prepared
            ]
            replaced_sizes = list(
                session.scalars(
                    select(materials.c.size).where(
                        materials.c.owner_id == owner_id,
                        or_(*identities),
                    )
                )
            )
            projected_count = int(total_count) - len(replaced_sizes) + len(prepared)
            projected_bytes = (
                int(total_bytes)
                - sum(int(size) for size in replaced_sizes)
                + sum(record.size for record, _, _ in prepared)
            )
            if projected_count > max_count or projected_bytes > max_bytes:
                raise MaterialQuotaExceededError("The learner material quota would be exceeded")
            self._write_prepared(
                session=session,
                owner_id=owner_id,
                prepared=prepared,
                embeddings=embeddings,
            )
        return [record for record, _, _ in prepared]

    def _prepare_documents(
        self,
        *,
        owner_id: str,
        documents: list[MaterialDocument],
    ) -> tuple[str, list[tuple[MaterialRecord, MaterialDocument, list[str]]]]:
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
                title=document.filename,
                tags=[],
                content_type=document.content_type,
                size=len(encoded) if document.size is None else document.size,
                status="indexed",
                chunk_count=len(chunks),
                content_sha256=sha256(encoded).hexdigest(),
                indexed_at=indexed_at,
            )
            prepared.append((record, document, chunks))
        return owner_id, prepared

    def _embed_prepared(
        self,
        prepared: list[tuple[MaterialRecord, MaterialDocument, list[str]]],
    ) -> list[list[float] | None]:
        all_chunks = [chunk for _, _, chunks in prepared for chunk in chunks]
        return self._embed_or_none(all_chunks)

    @staticmethod
    def _write_prepared(
        *,
        session,
        owner_id: str,
        prepared: list[tuple[MaterialRecord, MaterialDocument, list[str]]],
        embeddings: list[list[float] | None],
    ) -> None:
        vectors = iter(embeddings)
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
                    title=record.title,
                    tags=record.tags,
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
                        "embedding": next(vectors),
                    }
                    for index, chunk in enumerate(chunks)
                ],
            )

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
        terms = _lexical_terms(query_lower)
        if not terms:
            raise ValueError("Search query must contain a word")
        score = sum(content_lower.count(term) for term in terms)
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
        except Exception as error:
            logger.warning(
                "Query embedding failed; lexical retrieval remains available (%s)",
                type(error).__name__,
            )
            return None

    def backfill_embeddings(self) -> int:
        """Fill missing vectors in bounded batches and stop cleanly on provider failure."""

        if self.embedder is None:
            return 0
        updated_count = 0
        with self._lock_for("__embedding_backfill__"):
            while True:
                with self.database.session() as session:
                    rows = session.execute(
                        select(
                            material_chunks.c.owner_id,
                            material_chunks.c.project_id,
                            material_chunks.c.material_id,
                            material_chunks.c.chunk_index,
                            material_chunks.c.content,
                        )
                        .where(material_chunks.c.embedding.is_(None))
                        .order_by(
                            material_chunks.c.owner_id,
                            material_chunks.c.project_id,
                            material_chunks.c.material_id,
                            material_chunks.c.chunk_index,
                        )
                        .limit(self.embedding_batch_size)
                    ).all()
                if not rows:
                    break
                vectors = self._embed_or_none([row.content for row in rows])
                successful = [
                    (row, vector)
                    for row, vector in zip(rows, vectors, strict=True)
                    if vector is not None
                ]
                if not successful:
                    break
                with self.database.session() as session:
                    for row, vector in successful:
                        session.execute(
                            update(material_chunks)
                            .where(
                                material_chunks.c.owner_id == row.owner_id,
                                material_chunks.c.project_id == row.project_id,
                                material_chunks.c.material_id == row.material_id,
                                material_chunks.c.chunk_index == row.chunk_index,
                                material_chunks.c.embedding.is_(None),
                            )
                            .values(embedding=vector)
                        )
                updated_count += len(successful)
        return updated_count

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
        query = query.strip()
        if not query:
            raise ValueError("Search query must contain a word")
        lexical_terms = _lexical_terms(query)
        if not lexical_terms:
            raise ValueError("Search query must contain a word")
        bounded_limit = max(1, min(limit, 50))
        candidate_limit = max(50, bounded_limit * 8)
        query_embedding = self._query_embedding(query)
        with self.database.session() as session:
            scope = (
                material_chunks.c.owner_id == owner_id,
                material_chunks.c.project_id == project_id,
            )
            database_scores: dict[tuple[str, int], float] = {}
            lexical_by_key: dict[tuple[str, int], float] = {}
            if self.database.is_postgresql:
                search_config = literal_column("'simple'::regconfig")
                search_query = func.websearch_to_tsquery(search_config, query)
                search_document = func.to_tsvector(search_config, material_chunks.c.content)
                escaped_terms = (
                    term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                    for term in lexical_terms
                )
                substring_match = or_(
                    *(
                        material_chunks.c.content.ilike(
                            f"%{term}%",
                            escape="\\",
                        )
                        for term in escaped_terms
                    )
                )
                lexical_rank = func.greatest(
                    func.ts_rank_cd(search_document, search_query),
                    case((substring_match, 1.0), else_=0.0),
                )
                lexical_rows = session.execute(
                    select(material_chunks, lexical_rank.label("lexical_score"))
                    .where(*scope, or_(search_document.op("@@")(search_query), substring_match))
                    .order_by(lexical_rank.desc())
                    .limit(candidate_limit)
                ).all()
                rows_by_key = {(row.material_id, int(row.chunk_index)): row for row in lexical_rows}
                lexical_by_key = {
                    (row.material_id, int(row.chunk_index)): float(row.lexical_score)
                    for row in lexical_rows
                }
                if query_embedding is not None:
                    distance = _postgres_cosine_distance(
                        material_chunks.c.embedding,
                        query_embedding,
                    )
                    semantic_rows = session.execute(
                        select(material_chunks, (1 - distance).label("semantic_score"))
                        .where(*scope, material_chunks.c.embedding.is_not(None))
                        .order_by(distance)
                        .limit(candidate_limit)
                    ).all()
                    for row in semantic_rows:
                        key = (row.material_id, int(row.chunk_index))
                        rows_by_key.setdefault(key, row)
                        database_scores[key] = float(row.semantic_score)
                rows = list(rows_by_key.values())
            else:
                rows = session.execute(select(material_chunks).where(*scope)).all()

        scored: list[tuple[float, object]] = []
        if self.database.is_postgresql:
            lexical_scores = [
                lexical_by_key.get((row.material_id, int(row.chunk_index)), 0.0) for row in rows
            ]
        else:
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
            for score, row in scored[:bounded_limit]
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

    def material_chunks(
        self,
        *,
        owner_id: str,
        project_id: str,
        material_id: str,
        limit: int = 24,
    ) -> list[SearchResult]:
        """Return evenly sampled chunks for bounded whole-document analysis."""

        owner_id = validate_identifier(owner_id, field="owner_id")
        project_id = validate_identifier(project_id, field="project_id")
        material_id = validate_identifier(material_id, field="material_id")
        bounded_limit = max(1, min(limit, 100))
        with self.database.session() as session:
            rows = session.execute(
                select(material_chunks)
                .where(
                    material_chunks.c.owner_id == owner_id,
                    material_chunks.c.project_id == project_id,
                    material_chunks.c.material_id == material_id,
                )
                .order_by(material_chunks.c.chunk_index)
            ).all()
        if not rows:
            raise MaterialNotFoundError(material_id)
        if len(rows) > bounded_limit:
            indexes = {
                round(position * (len(rows) - 1) / (bounded_limit - 1))
                for position in range(bounded_limit)
            } if bounded_limit > 1 else {0}
            rows = [row for index, row in enumerate(rows) if index in indexes]
        return [
            SearchResult(
                citation_id=f"{row.material_id}#{row.chunk_index}",
                material_id=row.material_id,
                filename=row.filename,
                chunk_index=int(row.chunk_index),
                text=row.content,
                score=1.0,
            )
            for row in rows
        ]

    def get_material_storage_key(
        self,
        *,
        owner_id: str,
        project_id: str,
        material_id: str,
    ) -> str:
        owner_id = validate_identifier(owner_id, field="owner_id")
        project_id = validate_identifier(project_id, field="project_id")
        material_id = validate_identifier(material_id, field="material_id")
        with self.database.session() as session:
            storage_key = session.scalar(
                select(materials.c.storage_key).where(
                    materials.c.owner_id == owner_id,
                    materials.c.project_id == project_id,
                    materials.c.material_id == material_id,
                )
            )
        if not storage_key:
            raise MaterialNotFoundError(material_id)
        return str(storage_key)

    def delete_material(
        self,
        *,
        owner_id: str,
        project_id: str,
        material_id: str,
    ) -> str:
        deleted = self.delete_materials(
            owner_id=owner_id,
            project_id=project_id,
            material_ids=[material_id],
        )
        return deleted[0][1]

    def delete_materials(
        self,
        *,
        owner_id: str,
        project_id: str,
        material_ids: list[str],
    ) -> list[tuple[MaterialRecord, str]]:
        """Delete a validated owner-scoped material selection in one transaction."""

        owner_id = validate_identifier(owner_id, field="owner_id")
        project_id = validate_identifier(project_id, field="project_id")
        normalized_ids = [
            validate_identifier(material_id, field="material_id") for material_id in material_ids
        ]
        if not normalized_ids:
            raise ValueError("At least one material ID is required")
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("Material IDs must be unique")
        with self._lock_for(owner_id), self.database.session() as session:
            self._lock_owner_write(session, owner_id)
            rows = session.execute(
                select(materials).where(
                    materials.c.owner_id == owner_id,
                    materials.c.project_id == project_id,
                    materials.c.material_id.in_(normalized_ids),
                )
            ).all()
            by_id = {row.material_id: row for row in rows}
            if len(by_id) != len(normalized_ids):
                missing = next(
                    material_id for material_id in normalized_ids if material_id not in by_id
                )
                raise MaterialNotFoundError(missing)
            session.execute(
                delete(material_chunks).where(
                    material_chunks.c.owner_id == owner_id,
                    material_chunks.c.project_id == project_id,
                    material_chunks.c.material_id.in_(normalized_ids),
                )
            )
            deleted = session.execute(
                delete(materials).where(
                    materials.c.owner_id == owner_id,
                    materials.c.project_id == project_id,
                    materials.c.material_id.in_(normalized_ids),
                )
            )
            if deleted.rowcount != len(normalized_ids):
                raise MaterialNotFoundError(normalized_ids[0])
        return [
            (self._material_record(by_id[material_id]), str(by_id[material_id].storage_key))
            for material_id in normalized_ids
        ]

    def update_material_metadata(
        self,
        *,
        owner_id: str,
        project_id: str,
        material_id: str,
        title: str | None = None,
        tags: list[str] | None = None,
    ) -> MaterialRecord:
        owner_id = validate_identifier(owner_id, field="owner_id")
        project_id = validate_identifier(project_id, field="project_id")
        material_id = validate_identifier(material_id, field="material_id")
        values: dict[str, object] = {}
        if title is not None:
            values["title"] = title
        if tags is not None:
            values["tags"] = tags
        if not values:
            raise ValueError("At least one metadata field is required")
        with self._lock_for(owner_id), self.database.session() as session:
            self._lock_owner_write(session, owner_id)
            changed = session.execute(
                update(materials)
                .where(
                    materials.c.owner_id == owner_id,
                    materials.c.project_id == project_id,
                    materials.c.material_id == material_id,
                )
                .values(**values)
            )
            if changed.rowcount != 1:
                raise MaterialNotFoundError(material_id)
            row = session.execute(
                select(materials).where(
                    materials.c.owner_id == owner_id,
                    materials.c.project_id == project_id,
                    materials.c.material_id == material_id,
                )
            ).one()
        return self._material_record(row)

    def list_materials(
        self,
        *,
        owner_id: str,
        project_id: str,
        status: str | None = None,
        tag: str | None = None,
        sort: str = "newest",
    ) -> list[MaterialRecord]:
        owner_id = validate_identifier(owner_id, field="owner_id")
        project_id = validate_identifier(project_id, field="project_id")
        filters = [
            materials.c.owner_id == owner_id,
            materials.c.project_id == project_id,
        ]
        if status is not None:
            filters.append(materials.c.status == status)
        with self.database.session() as session:
            rows = session.execute(select(materials).where(*filters)).all()
        records = [self._material_record(row) for row in rows]
        if tag is not None:
            normalized_tag = tag.casefold()
            records = [
                record
                for record in records
                if any(item.casefold() == normalized_tag for item in record.tags)
            ]
        if sort == "newest":
            return sorted(records, key=lambda record: (-record.indexed_at.timestamp(), record.id))
        if sort == "oldest":
            return sorted(records, key=lambda record: (record.indexed_at.timestamp(), record.id))
        if sort == "title":
            return sorted(records, key=lambda record: (record.title.casefold(), record.id))
        if sort == "size_desc":
            return sorted(records, key=lambda record: (-record.size, record.id))
        raise ValueError("Unsupported material sort order")
