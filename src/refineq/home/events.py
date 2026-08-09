"""Content-free observability and idempotent action receipts for home dispatch."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from refineq.home.models import HomeActionReceipt
from refineq.storage.json_store import (
    AtomicJsonStore,
    RecordAlreadyExistsError,
    RecordNotFoundError,
)


class HomeDispatchEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id_hash: str = Field(pattern=r"^[0-9a-f]{32}$")
    result_kind: Literal[
        "direct_answer",
        "open_workspace",
        "workspace_action",
        "propose_workspace",
        "clarify",
        "out_of_scope",
    ]
    decided_by: Literal["rule", "model", "hybrid"]
    latency_bucket: Literal["lt_1s", "1_6s", "6_18s", "gt_18s"]
    latency_ms: int = Field(ge=0)
    candidate_count: int = Field(ge=0, le=8)
    candidate_truncated: bool = False
    proposal_confirmed: bool | None = None
    error_code: str | None = Field(default=None, max_length=100)
    occurred_at: datetime

    @field_validator("occurred_at", mode="after")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value.astimezone(UTC)


def request_id_hash(request_id: str) -> str:
    return sha256(request_id.encode()).hexdigest()[:32]


def latency_bucket(latency_ms: int) -> Literal["lt_1s", "1_6s", "6_18s", "gt_18s"]:
    if latency_ms < 1_000:
        return "lt_1s"
    if latency_ms < 6_000:
        return "1_6s"
    if latency_ms < 18_000:
        return "6_18s"
    return "gt_18s"


class HomeEventRepository:
    def __init__(self, store: AtomicJsonStore, *, max_events: int = 1_000) -> None:
        if max_events < 1:
            raise ValueError("max_events must be positive")
        self._store = store
        self._max_events = max_events

    def record(self, owner_id: str, event: HomeDispatchEvent) -> HomeDispatchEvent:
        with self._store.owner_transaction(owner_id, "home-dispatch-events"):
            with suppress(RecordAlreadyExistsError):
                self._store.create(
                    owner_id,
                    "home_dispatch_events",
                    event.request_id_hash,
                    event.model_dump(mode="json"),
                )
            self._store.trim_collection(
                owner_id,
                "home_dispatch_events",
                self._max_events,
                order_field="occurred_at",
                record_id_field="request_id_hash",
            )
        return event

    def list(self, owner_id: str) -> list[HomeDispatchEvent]:
        return [
            HomeDispatchEvent.model_validate(record.data)
            for record in self._store.list(owner_id, "home_dispatch_events")
        ]

    def _mark_proposal_state(
        self,
        owner_id: str,
        request_id: str,
        *,
        confirmed: bool,
    ) -> HomeDispatchEvent | None:
        record_id = request_id_hash(request_id)
        with self._store.owner_transaction(owner_id, "home-dispatch-events"):
            try:
                record = self._store.read(owner_id, "home_dispatch_events", record_id)
            except RecordNotFoundError:
                return None
            current = HomeDispatchEvent.model_validate(record.data)
            if current.result_kind not in {"workspace_action", "propose_workspace"}:
                return None
            event = current.model_copy(update={"proposal_confirmed": confirmed})
            self._store.save(
                owner_id,
                "home_dispatch_events",
                record_id,
                event.model_dump(mode="json"),
                expected_version=record.version,
            )
        return event

    def mark_proposal_confirmed(
        self,
        owner_id: str,
        request_id: str,
    ) -> HomeDispatchEvent | None:
        return self._mark_proposal_state(owner_id, request_id, confirmed=True)

    def mark_proposal_cancelled(
        self,
        owner_id: str,
        request_id: str,
    ) -> HomeDispatchEvent | None:
        return self._mark_proposal_state(owner_id, request_id, confirmed=False)


class HomeReceiptRepository:
    def __init__(self, store: AtomicJsonStore) -> None:
        self._store = store

    @staticmethod
    def _record_id(idempotency_key: str) -> str:
        return sha256(idempotency_key.encode()).hexdigest()[:32]

    def get(self, owner_id: str, idempotency_key: str) -> HomeActionReceipt | None:
        try:
            record = self._store.read(
                owner_id,
                "home_action_receipts",
                self._record_id(idempotency_key),
            )
        except RecordNotFoundError:
            return None
        return HomeActionReceipt.model_validate(record.data)

    @contextmanager
    def transaction(self, owner_id: str, idempotency_key: str) -> Iterator[None]:
        """Serialize check, domain mutation, and receipt commit for one action."""

        scope = f"home-confirm-{self._record_id(idempotency_key)}"
        with self._store.owner_transaction(owner_id, scope):
            yield

    def save(self, owner_id: str, receipt: HomeActionReceipt) -> HomeActionReceipt:
        record_id = self._record_id(receipt.idempotency_key)
        try:
            self._store.create(
                owner_id,
                "home_action_receipts",
                record_id,
                receipt.model_dump(mode="json"),
            )
            return receipt
        except RecordAlreadyExistsError:
            existing = self.get(owner_id, receipt.idempotency_key)
            if existing is None:
                raise
            return existing
