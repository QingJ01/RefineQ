"""Durable, serial evaluation-run lease and idempotency storage."""

from __future__ import annotations

import base64
import hmac
import json
import secrets
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import case, delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from refineq.database.engine import Database
from refineq.database.schema import mcp_evaluation_idempotency, mcp_evaluation_runs
from refineq.knowledge.index import KnowledgeIndex, MaterialNotFoundError
from refineq.learning.service import LearningConflictError, LearningService, SeedRequest, TopicSeed
from refineq.storage.journey_events import JourneyEventRepository
from refineq.storage.json_store import RecordAlreadyExistsError, RecordNotFoundError
from refineq.storage.learning import LearningRepository
from refineq.storage.sessions import SessionRepository
from refineq.storage.workspaces import WorkspaceRepository

SEED_VERSION = "phase-a-v1"
ACTIVE_SLOT = "evaluation"
EVALUATION_LOGICAL_NOW = datetime(2030, 1, 2, 9, 0, tzinfo=UTC)
_RUN_FENCE_KEY = "_scope_fence"
_IDEMPOTENCY_PENDING = {"_refineq_state": "pending"}


class SandboxError(RuntimeError):
    code = "sandbox_error"


class DemoBusyError(SandboxError):
    code = "demo_busy"


class RunNotFoundError(SandboxError):
    code = "run_not_found"


class RunExpiredError(SandboxError):
    code = "run_expired"


class RunCompletedError(SandboxError):
    code = "run_completed"


class IdempotencyConflictError(SandboxError):
    code = "idempotency_conflict"


@dataclass(frozen=True, slots=True)
class DemoRun:
    run_token: str
    run_fence: str
    status: str
    seed_version: str
    expires_at: datetime
    replayed: bool = False


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


class McpSandboxRepository:
    """Persist no raw credentials while enforcing one globally active demo."""

    def __init__(
        self,
        database: Database,
        *,
        secret: str,
        principal_id: str,
        run_ttl: timedelta,
        idempotency_ttl: timedelta,
    ) -> None:
        self._database = database
        self._secret = secret.encode("utf-8")
        self.principal_id = principal_id
        self._run_ttl = run_ttl
        self._idempotency_ttl = idempotency_ttl

    def _hmac(self, purpose: str, value: str) -> str:
        return hmac.new(
            self._secret,
            f"{purpose}:{value}".encode(),
            sha256,
        ).hexdigest()

    def _token_for(self, client_run_key: str, generation: str) -> str:
        token_input = (
            f"run-token:{SEED_VERSION}:{client_run_key}"
            if generation == "legacy"
            else f"run-token:{SEED_VERSION}:{generation}:{client_run_key}"
        )
        digest = hmac.new(
            self._secret,
            token_input.encode(),
            sha256,
        ).digest()
        encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return f"mcp_run_{encoded}"

    def _fence_for(self, run_token: str) -> str:
        return self._hmac("run-fence", run_token)

    def public_question_id(self, run_token: str, domain_question_id: str) -> str:
        """Return an opaque question id that cannot be replayed in another run."""

        return f"mcp_q_{self._hmac(f'question:{run_token}', domain_question_id)[:32]}"

    def domain_idempotency_id(self, run_token: str, tool_name: str, external_key: str) -> str:
        """Derive a non-reversible domain key without persisting caller identifiers."""

        purpose = f"domain-idempotency:{run_token}:{tool_name}"
        return f"mcp_idem_{self._hmac(purpose, external_key)[:40]}"

    def recover_startup(self, *, now: datetime | None = None) -> int:
        """Release runs interrupted while their sandbox baseline was being seeded."""

        observed_at = _utc(now or datetime.now(UTC))
        with self._database.session() as session:
            changed = session.execute(
                update(mcp_evaluation_runs)
                .where(
                    mcp_evaluation_runs.c.principal_id == self.principal_id,
                    mcp_evaluation_runs.c.status == "seeding",
                    mcp_evaluation_runs.c.expires_at <= observed_at,
                )
                .values(
                    status="failed",
                    active_slot=None,
                    updated_at=observed_at,
                    last_error_code="startup_interrupted",
                )
            )
            return int(changed.rowcount or 0)

    @staticmethod
    def _run_hash(run_token: str) -> str:
        return sha256(run_token.encode("utf-8")).hexdigest()

    def begin(self, client_run_key: str, *, now: datetime | None = None) -> DemoRun:
        observed_at = _utc(now or datetime.now(UTC))
        expires_at = observed_at + self._run_ttl
        generation = secrets.token_hex(16)
        token = self._token_for(client_run_key, generation)
        run_hash = self._run_hash(token)
        client_hash = self._hmac("client-run-key", client_run_key)
        # A same-key replay is read-only. Resolve it before the maintenance
        # writes below so concurrent callers do not queue behind an unrelated
        # SQLite writer while the winning worker seeds the sandbox.
        with self._database.session() as session:
            existing = session.execute(
                select(mcp_evaluation_runs).where(
                    mcp_evaluation_runs.c.principal_id == self.principal_id,
                    mcp_evaluation_runs.c.client_run_key_hash == client_hash,
                )
            ).one_or_none()
        if existing is not None:
            existing_expiry = _utc(existing.expires_at)
            if (
                str(existing.seed_version) == SEED_VERSION
                and existing.status in {"seeding", "active"}
                and existing_expiry > observed_at
            ):
                token = self._token_for(client_run_key, str(existing.generation))
                return DemoRun(
                    run_token=token,
                    run_fence=self._fence_for(token),
                    status=str(existing.status),
                    seed_version=str(existing.seed_version),
                    expires_at=existing_expiry,
                    replayed=True,
                )
        try:
            with self._database.session() as session:
                session.execute(
                    delete(mcp_evaluation_runs).where(
                        mcp_evaluation_runs.c.principal_id == self.principal_id,
                        mcp_evaluation_runs.c.active_slot.is_(None),
                        mcp_evaluation_runs.c.status.in_(
                            {"completed", "released", "expired", "failed"}
                        ),
                        mcp_evaluation_runs.c.updated_at <= observed_at - self._idempotency_ttl,
                    )
                )
                session.execute(
                    update(mcp_evaluation_runs)
                    .where(
                        mcp_evaluation_runs.c.active_slot == ACTIVE_SLOT,
                        mcp_evaluation_runs.c.expires_at <= observed_at,
                    )
                    .values(
                        status=case(
                            (mcp_evaluation_runs.c.status == "seeding", "failed"),
                            else_="expired",
                        ),
                        active_slot=None,
                        updated_at=observed_at,
                        last_error_code=case(
                            (
                                mcp_evaluation_runs.c.status == "seeding",
                                "seeding_lease_expired",
                            ),
                            else_=mcp_evaluation_runs.c.last_error_code,
                        ),
                    )
                )
                existing = session.execute(
                    select(mcp_evaluation_runs).where(
                        mcp_evaluation_runs.c.principal_id == self.principal_id,
                        mcp_evaluation_runs.c.client_run_key_hash == client_hash,
                    )
                ).one_or_none()
                if existing is not None:
                    if str(existing.seed_version) != SEED_VERSION:
                        raise IdempotencyConflictError(
                            "The client run key belongs to a different seed version"
                        )
                    generation = str(existing.generation)
                    token = self._token_for(client_run_key, generation)
                    existing_expiry = _utc(existing.expires_at)
                    if existing.status in {"seeding", "active"} and existing_expiry > observed_at:
                        return DemoRun(
                            run_token=token,
                            run_fence=self._fence_for(token),
                            status=str(existing.status),
                            seed_version=str(existing.seed_version),
                            expires_at=existing_expiry,
                            replayed=True,
                        )
                    if existing.status == "failed":
                        active = session.scalar(
                            select(mcp_evaluation_runs.c.run_id_hash).where(
                                mcp_evaluation_runs.c.active_slot == ACTIVE_SLOT
                            )
                        )
                        if active is not None:
                            raise DemoBusyError("Another evaluation run is active")
                        claimed = session.execute(
                            update(mcp_evaluation_runs)
                            .where(
                                mcp_evaluation_runs.c.run_id_hash == existing.run_id_hash,
                                mcp_evaluation_runs.c.status == "failed",
                                mcp_evaluation_runs.c.active_slot.is_(None),
                            )
                            .values(
                                status="seeding",
                                active_slot=ACTIVE_SLOT,
                                updated_at=observed_at,
                                expires_at=expires_at,
                                last_error_code=None,
                            )
                        )
                        if claimed.rowcount != 1:
                            canonical = session.execute(
                                select(mcp_evaluation_runs).where(
                                    mcp_evaluation_runs.c.run_id_hash == existing.run_id_hash
                                )
                            ).one()
                            canonical_expiry = _utc(canonical.expires_at)
                            if (
                                canonical.status in {"seeding", "active"}
                                and canonical_expiry > observed_at
                            ):
                                return DemoRun(
                                    run_token=token,
                                    run_fence=self._fence_for(token),
                                    status=str(canonical.status),
                                    seed_version=str(canonical.seed_version),
                                    expires_at=canonical_expiry,
                                    replayed=True,
                                )
                            raise DemoBusyError("Another evaluation run is active")
                        return DemoRun(
                            run_token=token,
                            run_fence=self._fence_for(token),
                            status="seeding",
                            seed_version=str(existing.seed_version),
                            expires_at=expires_at,
                        )
                    raise RunCompletedError("Use a new client_run_key for a new demo")
                active = session.scalar(
                    select(mcp_evaluation_runs.c.run_id_hash).where(
                        mcp_evaluation_runs.c.active_slot == ACTIVE_SLOT
                    )
                )
                if active is not None:
                    raise DemoBusyError("Another evaluation run is active")
                session.execute(
                    insert(mcp_evaluation_runs).values(
                        run_id_hash=run_hash,
                        client_run_key_hash=client_hash,
                        principal_id=self.principal_id,
                        status="seeding",
                        active_slot=ACTIVE_SLOT,
                        seed_version=SEED_VERSION,
                        generation=generation,
                        created_at=observed_at,
                        updated_at=observed_at,
                        expires_at=expires_at,
                    )
                )
        except IntegrityError as error:
            # Two workers can observe the same missing client key and race the
            # unique insert. The loser must replay the canonical row instead of
            # misreporting a global-slot conflict.
            with self._database.session() as session:
                existing = session.execute(
                    select(mcp_evaluation_runs).where(
                        mcp_evaluation_runs.c.principal_id == self.principal_id,
                        mcp_evaluation_runs.c.client_run_key_hash == client_hash,
                    )
                ).one_or_none()
            if existing is not None:
                token = self._token_for(client_run_key, str(existing.generation))
                existing_expiry = _utc(existing.expires_at)
                if (
                    str(existing.seed_version) == SEED_VERSION
                    and existing.status in {"seeding", "active"}
                    and existing_expiry > observed_at
                ):
                    return DemoRun(
                        run_token=token,
                        run_fence=self._fence_for(token),
                        status=str(existing.status),
                        seed_version=str(existing.seed_version),
                        expires_at=existing_expiry,
                        replayed=True,
                    )
            raise DemoBusyError("Another evaluation run is active") from error
        return DemoRun(
            run_token=token,
            run_fence=self._fence_for(token),
            status="seeding",
            seed_version=SEED_VERSION,
            expires_at=expires_at,
        )

    def _row(self, session: Any, run_token: str):
        return session.execute(
            select(mcp_evaluation_runs).where(
                mcp_evaluation_runs.c.run_id_hash == self._run_hash(run_token),
                mcp_evaluation_runs.c.principal_id == self.principal_id,
            )
        ).one_or_none()

    def require_active(
        self,
        run_token: str,
        *,
        now: datetime | None = None,
    ) -> DemoRun:
        observed_at = _utc(now or datetime.now(UTC))
        with self._database.session() as session:
            row = self._row(session, run_token)
            if row is None:
                raise RunNotFoundError("Evaluation run not found")
            expires_at = _utc(row.expires_at)
            if expires_at <= observed_at:
                if row.active_slot is not None:
                    session.execute(
                        update(mcp_evaluation_runs)
                        .where(mcp_evaluation_runs.c.run_id_hash == row.run_id_hash)
                        .values(
                            status="expired",
                            active_slot=None,
                            updated_at=observed_at,
                        )
                    )
                raise RunExpiredError("Evaluation run expired")
            if row.status == "completed":
                raise RunCompletedError("Evaluation run is complete")
            if row.status != "active":
                raise RunNotFoundError("Evaluation run is not active")
            return DemoRun(
                run_token=run_token,
                run_fence=self._fence_for(run_token),
                status="active",
                seed_version=str(row.seed_version),
                expires_at=expires_at,
            )

    def require_seeding(
        self,
        run_token: str,
        *,
        now: datetime | None = None,
    ) -> DemoRun:
        """Require the caller to still own the live sandbox-reset lease."""

        observed_at = _utc(now or datetime.now(UTC))
        with self._database.session() as session:
            row = self._row(session, run_token)
            if row is None:
                raise RunNotFoundError("Evaluation run not found")
            expires_at = _utc(row.expires_at)
            if expires_at <= observed_at:
                raise RunExpiredError("Evaluation run expired while seeding")
            if row.status != "seeding" or row.active_slot != ACTIVE_SLOT:
                raise RunNotFoundError("Evaluation run is not seeding")
            return DemoRun(
                run_token=run_token,
                run_fence=self._fence_for(run_token),
                status="seeding",
                seed_version=str(row.seed_version),
                expires_at=expires_at,
            )

    def activate(self, run_token: str, *, now: datetime | None = None) -> None:
        observed_at = _utc(now or datetime.now(UTC))
        with self._database.session() as session:
            changed = session.execute(
                update(mcp_evaluation_runs)
                .where(
                    mcp_evaluation_runs.c.run_id_hash == self._run_hash(run_token),
                    mcp_evaluation_runs.c.principal_id == self.principal_id,
                    mcp_evaluation_runs.c.status == "seeding",
                    mcp_evaluation_runs.c.active_slot == ACTIVE_SLOT,
                    mcp_evaluation_runs.c.expires_at > observed_at,
                )
                .values(status="active", updated_at=observed_at)
            )
            if changed.rowcount != 1:
                row = self._row(session, run_token)
                if row is None or row.status != "active":
                    raise RunNotFoundError("Evaluation run could not be activated")

    def fail(
        self,
        run_token: str,
        *,
        error_code: str,
        now: datetime | None = None,
    ) -> None:
        observed_at = _utc(now or datetime.now(UTC))
        with self._database.session() as session:
            session.execute(
                update(mcp_evaluation_runs)
                .where(
                    mcp_evaluation_runs.c.run_id_hash == self._run_hash(run_token),
                    mcp_evaluation_runs.c.principal_id == self.principal_id,
                    mcp_evaluation_runs.c.status == "seeding",
                    mcp_evaluation_runs.c.active_slot == ACTIVE_SLOT,
                )
                .values(
                    status="failed",
                    active_slot=None,
                    last_error_code=error_code,
                    updated_at=observed_at,
                )
            )

    def complete(self, run_token: str, *, now: datetime | None = None) -> None:
        observed_at = _utc(now or datetime.now(UTC))
        expired = False
        with self._database.session() as session:
            changed = session.execute(
                update(mcp_evaluation_runs)
                .where(
                    mcp_evaluation_runs.c.run_id_hash == self._run_hash(run_token),
                    mcp_evaluation_runs.c.principal_id == self.principal_id,
                    mcp_evaluation_runs.c.status == "active",
                    mcp_evaluation_runs.c.expires_at > observed_at,
                )
                .values(status="completed", active_slot=None, updated_at=observed_at)
            )
            if changed.rowcount != 1:
                row = self._row(session, run_token)
                if row is None:
                    raise RunNotFoundError("Evaluation run could not be completed")
                if row.status == "completed":
                    return
                if row.status == "expired" or (
                    row.status == "active" and _utc(row.expires_at) <= observed_at
                ):
                    session.execute(
                        update(mcp_evaluation_runs)
                        .where(
                            mcp_evaluation_runs.c.run_id_hash == row.run_id_hash,
                            mcp_evaluation_runs.c.status == "active",
                        )
                        .values(
                            status="expired",
                            active_slot=None,
                            updated_at=observed_at,
                        )
                    )
                    expired = True
                else:
                    raise RunNotFoundError("Evaluation run could not be completed")
        if expired:
            raise RunExpiredError("Evaluation run expired")

    def get_idempotency(
        self,
        run_token: str,
        *,
        tool_name: str,
        key: str,
        input_payload: Any,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        observed_at = _utc(now or datetime.now(UTC))
        run_hash = self._run_hash(run_token)
        key_hash = self._hmac(f"idempotency:{tool_name}", key)
        input_hash = _canonical_hash(input_payload)
        with self._database.session() as session:
            session.execute(
                delete(mcp_evaluation_idempotency).where(
                    mcp_evaluation_idempotency.c.retain_until <= observed_at
                )
            )
            row = session.execute(
                select(mcp_evaluation_idempotency).where(
                    mcp_evaluation_idempotency.c.principal_id == self.principal_id,
                    mcp_evaluation_idempotency.c.run_id_hash == run_hash,
                    mcp_evaluation_idempotency.c.tool_name == tool_name,
                    mcp_evaluation_idempotency.c.idempotency_key_hash == key_hash,
                )
            ).one_or_none()
        if row is None:
            return None
        if not hmac.compare_digest(str(row.input_hash), input_hash):
            raise IdempotencyConflictError("Idempotency key was used with different input")
        result = dict(row.result_json)
        return None if result == _IDEMPOTENCY_PENDING else result

    def claim_idempotency(
        self,
        run_token: str,
        *,
        tool_name: str,
        key: str,
        input_payload: Any,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Persist an input hash before a domain mutation and return a completed replay."""

        observed_at = _utc(now or datetime.now(UTC))
        run_hash = self._run_hash(run_token)
        key_hash = self._hmac(f"idempotency:{tool_name}", key)
        input_hash = _canonical_hash(input_payload)
        try:
            with self._database.session() as session:
                session.execute(
                    delete(mcp_evaluation_idempotency).where(
                        mcp_evaluation_idempotency.c.retain_until <= observed_at
                    )
                )
                row = session.execute(
                    select(mcp_evaluation_idempotency).where(
                        mcp_evaluation_idempotency.c.principal_id == self.principal_id,
                        mcp_evaluation_idempotency.c.run_id_hash == run_hash,
                        mcp_evaluation_idempotency.c.tool_name == tool_name,
                        mcp_evaluation_idempotency.c.idempotency_key_hash == key_hash,
                    )
                ).one_or_none()
                if row is not None:
                    if not hmac.compare_digest(str(row.input_hash), input_hash):
                        raise IdempotencyConflictError(
                            "Idempotency key was used with different input"
                        )
                    result = dict(row.result_json)
                    return None if result == _IDEMPOTENCY_PENDING else result
                session.execute(
                    insert(mcp_evaluation_idempotency).values(
                        principal_id=self.principal_id,
                        run_id_hash=run_hash,
                        tool_name=tool_name,
                        idempotency_key_hash=key_hash,
                        input_hash=input_hash,
                        result_json=_IDEMPOTENCY_PENDING,
                        created_at=observed_at,
                        retain_until=observed_at + self._idempotency_ttl,
                    )
                )
        except IntegrityError:
            return self.claim_idempotency(
                run_token,
                tool_name=tool_name,
                key=key,
                input_payload=input_payload,
                now=observed_at,
            )
        return None

    def save_idempotency(
        self,
        run_token: str,
        *,
        tool_name: str,
        key: str,
        input_payload: Any,
        result: dict[str, Any],
        now: datetime | None = None,
    ) -> None:
        observed_at = _utc(now or datetime.now(UTC))
        run_hash = self._run_hash(run_token)
        key_hash = self._hmac(f"idempotency:{tool_name}", key)
        input_hash = _canonical_hash(input_payload)
        try:
            with self._database.session() as session:
                row = session.execute(
                    select(mcp_evaluation_idempotency).where(
                        mcp_evaluation_idempotency.c.principal_id == self.principal_id,
                        mcp_evaluation_idempotency.c.run_id_hash == run_hash,
                        mcp_evaluation_idempotency.c.tool_name == tool_name,
                        mcp_evaluation_idempotency.c.idempotency_key_hash == key_hash,
                    )
                ).one_or_none()
                if row is not None:
                    if not hmac.compare_digest(str(row.input_hash), input_hash):
                        raise IdempotencyConflictError(
                            "Idempotency key was used with different input"
                        )
                    if dict(row.result_json) != _IDEMPOTENCY_PENDING:
                        return
                    session.execute(
                        update(mcp_evaluation_idempotency)
                        .where(mcp_evaluation_idempotency.c.id == row.id)
                        .values(
                            result_json=result,
                            retain_until=observed_at + self._idempotency_ttl,
                        )
                    )
                    return
                session.execute(
                    insert(mcp_evaluation_idempotency).values(
                        principal_id=self.principal_id,
                        run_id_hash=run_hash,
                        tool_name=tool_name,
                        idempotency_key_hash=key_hash,
                        input_hash=input_hash,
                        result_json=result,
                        created_at=observed_at,
                        retain_until=observed_at + self._idempotency_ttl,
                    )
                )
        except IntegrityError:
            replay = self.claim_idempotency(
                run_token,
                tool_name=tool_name,
                key=key,
                input_payload=input_payload,
                now=observed_at,
            )
            if replay is None:
                self.save_idempotency(
                    run_token,
                    tool_name=tool_name,
                    key=key,
                    input_payload=input_payload,
                    result=result,
                    now=observed_at,
                )


EVALUATION_WORKSPACE_ID = "mcp_evaluation_workspace"
EVALUATION_MATERIAL_ID = "mcp_evaluation_limits"
EVALUATION_TOPIC_ID = "function_limits"
EVALUATION_MATERIAL = """Function limits and continuity

A function limit describes the value that f(x) approaches as x approaches a point.
The limit depends on nearby values and does not require f(x) to equal that value at
the point. For example, define f(x) = (x^2 - 1)/(x - 1) when x is not 1, and set
f(1) = 9. Nearby values simplify to x + 1, so the limit as x approaches 1 is 2,
even though the assigned function value is 9. Continuity at a point requires the
limit to exist, the function value to exist, and those two values to be equal.
"""
EVALUATION_MATERIAL_HASH = sha256(EVALUATION_MATERIAL.encode()).hexdigest()
EVALUATION_WORKSPACE_TITLE = "Function Limits Evaluation"
EVALUATION_WORKSPACE_GOAL = "Explain and apply function limits using source evidence."


@dataclass(frozen=True, slots=True)
class EvaluationSandboxState:
    owner_id: str
    workspace_id: str
    material_id: str
    topic_id: str
    state_version: int


class EvaluationSandboxService:
    """Reset one dedicated workspace under the configured account to a curated baseline."""

    def __init__(
        self,
        *,
        owner_id: str,
        account_email: str,
        workspaces: WorkspaceRepository,
        learning: LearningRepository,
        learning_service: LearningService,
        journey_events: JourneyEventRepository,
        sessions: SessionRepository,
        knowledge: KnowledgeIndex,
    ) -> None:
        self._owner_id_value = owner_id
        self.account_email = account_email
        self._workspaces = workspaces
        self._learning = learning
        self._learning_service = learning_service
        self._journey_events = journey_events
        self._sessions = sessions
        self._knowledge = knowledge

    @property
    def owner_id(self) -> str:
        """Return the server-bound owner without exposing account lookup to callers."""

        return self._owner_id_value

    def state(self, *, expected_run_fence: str | None = None) -> EvaluationSandboxState:
        record = self._learning.get(self._owner_id_value, EVALUATION_WORKSPACE_ID)
        if (
            expected_run_fence is not None
            and record.data.get("progress", {}).get(_RUN_FENCE_KEY) != expected_run_fence
        ):
            raise LearningConflictError("The evaluation sandbox belongs to a different run")
        return EvaluationSandboxState(
            owner_id=self._owner_id_value,
            workspace_id=EVALUATION_WORKSPACE_ID,
            material_id=EVALUATION_MATERIAL_ID,
            topic_id=EVALUATION_TOPIC_ID,
            state_version=record.version,
        )

    def _ensure_static_seed(self, *, owner_id: str, now: datetime) -> None:
        try:
            workspace = self._workspaces.get(owner_id, EVALUATION_WORKSPACE_ID)
        except RecordNotFoundError:
            try:
                workspace = self._workspaces.create(
                    owner_id,
                    EVALUATION_WORKSPACE_ID,
                    title=EVALUATION_WORKSPACE_TITLE,
                    subject="Calculus",
                    goal=EVALUATION_WORKSPACE_GOAL,
                    topics=["Function limits"],
                    keywords=["limit", "continuity", "approaches"],
                    routing_summary="Fixed Phase A evaluation workspace.",
                    now=now,
                )
            except RecordAlreadyExistsError:
                workspace = self._workspaces.get(owner_id, EVALUATION_WORKSPACE_ID)
        if (
            workspace.title != EVALUATION_WORKSPACE_TITLE
            or workspace.subject != "Calculus"
            or workspace.goal != EVALUATION_WORKSPACE_GOAL
            or workspace.topics != ["Function limits"]
            or workspace.archived
        ):
            raise SandboxError("The fixed evaluation workspace does not match its seed")

        try:
            material = self._knowledge.get_material(
                owner_id=owner_id,
                project_id="library",
                material_id=EVALUATION_MATERIAL_ID,
            )
        except MaterialNotFoundError:
            material = self._knowledge.add_document(
                owner_id=owner_id,
                project_id="library",
                material_id=EVALUATION_MATERIAL_ID,
                filename="function-limits-evaluation.txt",
                text=EVALUATION_MATERIAL,
            )
        if (
            material.status != "indexed"
            or material.filename != "function-limits-evaluation.txt"
            or material.content_sha256 != EVALUATION_MATERIAL_HASH
            or material.chunk_count < 1
        ):
            raise SandboxError("The fixed evaluation material does not match its seed")
        chunks = self._knowledge.material_chunks(
            owner_id=owner_id,
            project_id="library",
            material_id=EVALUATION_MATERIAL_ID,
            limit=2,
        )
        if len(chunks) != 1 or chunks[0].text != EVALUATION_MATERIAL.strip():
            raise SandboxError("The fixed evaluation material chunks do not match its seed")

        linked = self._knowledge.list_materials(
            owner_id=owner_id,
            project_id=EVALUATION_WORKSPACE_ID,
        )
        linked_ids = {item.id for item in linked}
        if linked_ids - {EVALUATION_MATERIAL_ID}:
            raise SandboxError("The evaluation workspace contains unexpected material links")
        if EVALUATION_MATERIAL_ID not in linked_ids:
            self._knowledge.link_material(
                owner_id=owner_id,
                workspace_id=EVALUATION_WORKSPACE_ID,
                material_id=EVALUATION_MATERIAL_ID,
            )

    def _validate_static_seed(self, *, owner_id: str) -> None:
        self._workspaces.get(owner_id, EVALUATION_WORKSPACE_ID)
        material = self._knowledge.get_material(
            owner_id=owner_id,
            project_id=EVALUATION_WORKSPACE_ID,
            material_id=EVALUATION_MATERIAL_ID,
        )
        if material.status != "indexed" or material.content_sha256 != EVALUATION_MATERIAL_HASH:
            raise SandboxError("The evaluation material became unavailable during reset")
        chunks = self._knowledge.material_chunks(
            owner_id=owner_id,
            project_id=EVALUATION_WORKSPACE_ID,
            material_id=EVALUATION_MATERIAL_ID,
            limit=2,
        )
        if len(chunks) != 1 or chunks[0].text != EVALUATION_MATERIAL.strip():
            raise SandboxError("The evaluation material changed during reset")

    def ensure_seed(self, *, now: datetime | None = None) -> EvaluationSandboxState:
        """Idempotently provision static resources without creating learning state."""

        observed_at = _utc(now or datetime.now(UTC))
        owner_id = self._owner_id_value
        self._ensure_static_seed(owner_id=owner_id, now=observed_at)
        material = self._knowledge.get_material(
            owner_id=owner_id,
            project_id=EVALUATION_WORKSPACE_ID,
            material_id=EVALUATION_MATERIAL_ID,
        )
        return EvaluationSandboxState(
            owner_id=owner_id,
            workspace_id=EVALUATION_WORKSPACE_ID,
            material_id=material.id,
            topic_id=EVALUATION_TOPIC_ID,
            state_version=0,
        )

    def reset(
        self,
        *,
        now: datetime | None = None,
        run_fence: str | None = None,
        scope_guard: Callable[[], None] | None = None,
    ) -> EvaluationSandboxState:
        observed_at = _utc(now or datetime.now(UTC))
        logical_now = EVALUATION_LOGICAL_NOW
        effective_fence = run_fence or sha256(SEED_VERSION.encode()).hexdigest()
        owner_id = self.ensure_seed(now=observed_at).owner_id
        with self._learning.plan_transaction(owner_id, EVALUATION_WORKSPACE_ID):
            if scope_guard is not None:
                scope_guard()
            self._validate_static_seed(owner_id=owner_id)
            with suppress(RecordNotFoundError):
                self._learning.delete(owner_id, EVALUATION_WORKSPACE_ID)
            with suppress(RecordNotFoundError):
                self._journey_events.delete(owner_id, EVALUATION_WORKSPACE_ID)
            self._sessions.delete_for_workspace(owner_id, EVALUATION_WORKSPACE_ID)
            self._learning_service.seed(
                owner_id,
                EVALUATION_WORKSPACE_ID,
                SeedRequest(
                    goal=EVALUATION_WORKSPACE_GOAL,
                    exam_at=logical_now + timedelta(days=14),
                    daily_minutes=20,
                    topics=[TopicSeed(id=EVALUATION_TOPIC_ID, name="Function limits")],
                ),
            )
            self._learning_service.create_plan(
                owner_id,
                EVALUATION_WORKSPACE_ID,
                start_at=logical_now,
            )

            def bind_run_fence(data: dict[str, Any]) -> dict[str, Any]:
                data["progress"][_RUN_FENCE_KEY] = effective_fence
                return data

            self._learning.mutate(owner_id, EVALUATION_WORKSPACE_ID, bind_run_fence)
            self._validate_static_seed(owner_id=owner_id)
            if scope_guard is not None:
                scope_guard()
        record = self._learning.get(owner_id, EVALUATION_WORKSPACE_ID)
        return EvaluationSandboxState(
            owner_id=owner_id,
            workspace_id=EVALUATION_WORKSPACE_ID,
            material_id=EVALUATION_MATERIAL_ID,
            topic_id=EVALUATION_TOPIC_ID,
            state_version=record.version,
        )
