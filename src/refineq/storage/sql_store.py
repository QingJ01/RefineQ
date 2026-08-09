"""PostgreSQL/SQLAlchemy implementation of the owner-scoped record contract."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from hashlib import blake2b
from threading import Lock, RLock
from typing import Any

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from refineq.database.engine import Database
from refineq.database.owner_state import lock_writable_owner
from refineq.database.schema import records, utc_now
from refineq.storage.json_store import (
    RecordAlreadyExistsError,
    RecordNotFoundError,
    StaleVersionError,
    StoredRecord,
    validate_identifier,
)


class SqlRecordStore:
    """Persist versioned records in SQL without changing domain repositories."""

    _locks_guard = Lock()
    _locks: dict[str, RLock] = {}

    def __init__(self, database: Database, *, enforce_owner_state: bool = False) -> None:
        self.database = database
        self.enforce_owner_state = enforce_owner_state
        self._active_session: ContextVar[Session | None] = ContextVar(
            f"refineq_sql_store_session_{id(self)}",
            default=None,
        )

    @classmethod
    def _lock_for(cls, key: str) -> RLock:
        with cls._locks_guard:
            return cls._locks.setdefault(key, RLock())

    @contextmanager
    def _session(self) -> Iterator[Session]:
        active = self._active_session.get()
        if active is not None:
            yield active
            return
        with self.database.session() as session:
            yield session

    @staticmethod
    def _identity(owner_id: str, collection: str, record_id: str) -> dict[str, str]:
        return {
            "owner_id": validate_identifier(owner_id, field="owner_id"),
            "collection": validate_identifier(collection, field="collection"),
            "record_id": validate_identifier(record_id, field="record_id"),
        }

    @staticmethod
    def _stored(row: Any) -> StoredRecord:
        return StoredRecord(
            schema_version=int(row.schema_version),
            version=int(row.version),
            data=deepcopy(row.data),
        )

    @staticmethod
    def _advisory_key(owner_id: str, scope: str) -> int:
        digest = blake2b(f"{owner_id}:{scope}".encode(), digest_size=8).digest()
        return int.from_bytes(digest, "big", signed=True)

    def _lock_owner_write(self, session: Session, owner_id: str) -> None:
        if self.enforce_owner_state:
            lock_writable_owner(session, self.database, owner_id)

    @contextmanager
    def owner_transaction(self, owner_id: str, scope: str) -> Iterator[None]:
        owner_id = validate_identifier(owner_id, field="owner_id")
        scope = validate_identifier(scope, field="scope")
        lock_key = f"{owner_id}:{scope}"
        with self._lock_for(lock_key):
            active = self._active_session.get()
            if active is not None:
                if self.database.is_postgresql:
                    active.execute(
                        text("SELECT pg_advisory_xact_lock(:key)"),
                        {"key": self._advisory_key(owner_id, scope)},
                    )
                yield
                return
            with self.database.session() as session:
                if self.database.is_postgresql:
                    session.execute(
                        text("SELECT pg_advisory_xact_lock(:key)"),
                        {"key": self._advisory_key(owner_id, scope)},
                    )
                token = self._active_session.set(session)
                try:
                    yield
                finally:
                    self._active_session.reset(token)

    def create(
        self,
        owner_id: str,
        collection: str,
        record_id: str,
        data: dict[str, Any],
        *,
        schema_version: int = 1,
    ) -> StoredRecord:
        if schema_version < 1:
            raise ValueError("schema_version must be positive")
        identity = self._identity(owner_id, collection, record_id)
        lock_key = ":".join(identity.values())
        with self._lock_for(lock_key), self._session() as session:
            self._lock_owner_write(session, identity["owner_id"])
            if not self.database.is_postgresql:
                exists = session.scalar(select(records.c.record_id).filter_by(**identity))
                if exists is not None:
                    raise RecordAlreadyExistsError(lock_key)
                session.execute(
                    insert(records).values(
                        **identity,
                        schema_version=schema_version,
                        version=1,
                        data=deepcopy(data),
                        updated_at=utc_now(),
                    )
                )
                return StoredRecord(
                    schema_version=schema_version,
                    version=1,
                    data=deepcopy(data),
                )
            try:
                with session.begin_nested():
                    session.execute(
                        insert(records).values(
                            **identity,
                            schema_version=schema_version,
                            version=1,
                            data=deepcopy(data),
                            updated_at=utc_now(),
                        )
                    )
                    session.flush()
            except IntegrityError as error:
                raise RecordAlreadyExistsError(lock_key) from error
        return StoredRecord(schema_version=schema_version, version=1, data=deepcopy(data))

    def read(self, owner_id: str, collection: str, record_id: str) -> StoredRecord:
        identity = self._identity(owner_id, collection, record_id)
        with self._session() as session:
            row = session.execute(select(records).filter_by(**identity)).one_or_none()
            if row is None:
                raise RecordNotFoundError(":".join(identity.values()))
            return self._stored(row)

    def restore(
        self,
        owner_id: str,
        collection: str,
        record_id: str,
        record: StoredRecord,
    ) -> StoredRecord:
        """Restore an exact deleted record without overwriting a concurrent survivor."""

        identity = self._identity(owner_id, collection, record_id)
        lock_key = ":".join(identity.values())
        with self._lock_for(lock_key), self._session() as session:
            self._lock_owner_write(session, identity["owner_id"])
            statement = select(records).filter_by(**identity)
            if self.database.is_postgresql:
                statement = statement.with_for_update()
            row = session.execute(statement).one_or_none()
            if row is not None:
                return self._stored(row)

            try:
                with session.begin_nested():
                    session.execute(
                        insert(records).values(
                            **identity,
                            schema_version=record.schema_version,
                            version=record.version,
                            data=deepcopy(record.data),
                            updated_at=utc_now(),
                        )
                    )
                    session.flush()
            except IntegrityError:
                survivor = session.execute(select(records).filter_by(**identity)).one()
                return self._stored(survivor)
            return StoredRecord(
                schema_version=record.schema_version,
                version=record.version,
                data=deepcopy(record.data),
            )

    def delete(self, owner_id: str, collection: str, record_id: str) -> None:
        identity = self._identity(owner_id, collection, record_id)
        with self._lock_for(":".join(identity.values())), self._session() as session:
            session.execute(delete(records).filter_by(**identity))

    def list(self, owner_id: str, collection: str) -> list[StoredRecord]:
        return list(self.list_items(owner_id, collection).values())

    def list_items(self, owner_id: str, collection: str) -> dict[str, StoredRecord]:
        """Return valid records keyed by their owner-scoped record identifier."""

        owner_id = validate_identifier(owner_id, field="owner_id")
        collection = validate_identifier(collection, field="collection")
        with self._session() as session:
            rows = session.execute(
                select(records)
                .where(
                    records.c.owner_id == owner_id,
                    records.c.collection == collection,
                )
                .order_by(records.c.record_id)
            ).all()
            return {str(row.record_id): self._stored(row) for row in rows}

    def read_many(
        self,
        owner_id: str,
        collection: str,
        record_ids: list[str],
    ) -> dict[str, StoredRecord]:
        """Read selected owner-scoped records in one database round trip."""

        owner_id = validate_identifier(owner_id, field="owner_id")
        collection = validate_identifier(collection, field="collection")
        bounded_ids = list(
            dict.fromkeys(validate_identifier(item, field="record_id") for item in record_ids)
        )
        if not bounded_ids:
            return {}
        with self._session() as session:
            rows = session.execute(
                select(records).where(
                    records.c.owner_id == owner_id,
                    records.c.collection == collection,
                    records.c.record_id.in_(bounded_ids),
                )
            ).all()
        return {str(row.record_id): self._stored(row) for row in rows}

    def read_many_projection(
        self,
        owner_id: str,
        collection: str,
        record_ids: list[str],
        field_paths: tuple[tuple[str, ...], ...],
    ) -> dict[str, StoredRecord]:
        """Fetch only selected JSON fields in one database round trip."""

        owner_id = validate_identifier(owner_id, field="owner_id")
        collection = validate_identifier(collection, field="collection")
        bounded_ids = list(
            dict.fromkeys(validate_identifier(item, field="record_id") for item in record_ids)
        )
        if not bounded_ids:
            return {}
        projected_columns = []
        for index, path in enumerate(field_paths):
            expression = records.c.data
            for part in path:
                expression = expression[part]
            projected_columns.append(expression.label(f"field_{index}"))
        with self._session() as session:
            rows = session.execute(
                select(
                    records.c.record_id,
                    records.c.schema_version,
                    records.c.version,
                    *projected_columns,
                ).where(
                    records.c.owner_id == owner_id,
                    records.c.collection == collection,
                    records.c.record_id.in_(bounded_ids),
                )
            ).all()
        result: dict[str, StoredRecord] = {}
        for row in rows:
            data: dict[str, Any] = {}
            for index, path in enumerate(field_paths):
                value = getattr(row, f"field_{index}")
                if value is None:
                    continue
                target = data
                for part in path[:-1]:
                    target = target.setdefault(part, {})
                target[path[-1]] = deepcopy(value)
            result[str(row.record_id)] = StoredRecord(
                schema_version=int(row.schema_version),
                version=int(row.version),
                data=data,
            )
        return result

    def trim_collection(
        self,
        owner_id: str,
        collection: str,
        max_records: int,
        *,
        order_field: str,
        record_id_field: str,
    ) -> None:
        """Delete oldest records beyond a collection bound without loading payloads."""

        if max_records < 1:
            raise ValueError("max_records must be positive")
        owner_id = validate_identifier(owner_id, field="owner_id")
        collection = validate_identifier(collection, field="collection")
        order_field = validate_identifier(order_field, field="order_field")
        validate_identifier(record_id_field, field="record_id_field")
        with self._session() as session:
            where = (
                records.c.owner_id == owner_id,
                records.c.collection == collection,
            )
            total = int(session.scalar(select(func.count()).where(*where)) or 0)
            overflow = total - max_records
            if overflow <= 0:
                return
            oldest_ids = list(
                session.scalars(
                    select(records.c.record_id)
                    .where(*where)
                    .order_by(
                        records.c.data[order_field].as_string(),
                        records.c.record_id,
                    )
                    .limit(overflow)
                )
            )
            if oldest_ids:
                session.execute(delete(records).where(*where, records.c.record_id.in_(oldest_ids)))

    def save(
        self,
        owner_id: str,
        collection: str,
        record_id: str,
        data: dict[str, Any],
        *,
        expected_version: int,
    ) -> StoredRecord:
        identity = self._identity(owner_id, collection, record_id)
        lock_key = ":".join(identity.values())
        with self._lock_for(lock_key), self._session() as session:
            self._lock_owner_write(session, identity["owner_id"])
            statement = select(records).filter_by(**identity)
            if self.database.is_postgresql:
                statement = statement.with_for_update()
            row = session.execute(statement).one_or_none()
            if row is None:
                raise RecordNotFoundError(lock_key)
            if int(row.version) != expected_version:
                raise StaleVersionError(f"Expected version {expected_version}, found {row.version}")
            next_version = expected_version + 1
            session.execute(
                update(records)
                .filter_by(**identity)
                .values(
                    version=next_version,
                    data=deepcopy(data),
                    updated_at=utc_now(),
                )
            )
            return StoredRecord(
                schema_version=int(row.schema_version),
                version=next_version,
                data=deepcopy(data),
            )

    def mutate(
        self,
        owner_id: str,
        collection: str,
        record_id: str,
        transform: Callable[[dict[str, Any]], dict[str, Any]],
    ) -> StoredRecord:
        identity = self._identity(owner_id, collection, record_id)
        lock_key = ":".join(identity.values())
        with self._lock_for(lock_key), self._session() as session:
            self._lock_owner_write(session, identity["owner_id"])
            statement = select(records).filter_by(**identity)
            if self.database.is_postgresql:
                statement = statement.with_for_update()
            row = session.execute(statement).one_or_none()
            if row is None:
                raise RecordNotFoundError(lock_key)
            data = transform(deepcopy(row.data))
            if not isinstance(data, dict):
                raise TypeError("record transform must return a dictionary")
            next_version = int(row.version) + 1
            session.execute(
                update(records)
                .filter_by(**identity)
                .values(version=next_version, data=deepcopy(data), updated_at=utc_now())
            )
            return StoredRecord(
                schema_version=int(row.schema_version),
                version=next_version,
                data=deepcopy(data),
            )
