"""Administrator bootstrap and read-only operational control-plane services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import ceil

from sqlalchemy import case, func, insert, select

from refineq.config import Settings
from refineq.database.engine import Database
from refineq.database.schema import audit_logs, material_chunks, materials, records, users
from refineq.identity.models import User
from refineq.identity.service import IdentityService
from refineq.learning.events import learning_journey_metrics
from refineq.operations.backup import (
    BackupError,
    ManagedBackup,
    create_managed_backup,
    delete_managed_backup,
    list_managed_backups,
    validate_managed_backup,
)


@dataclass(frozen=True, slots=True)
class AdminBootstrapResult:
    user: User
    created: bool


class RestoreConfirmationError(RuntimeError):
    """Raised when a restore validation lacks the exact confirmation phrase."""


class AdminOperations:
    """Provide aggregate operations data without exposing filesystem paths."""

    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings
        self.backup_root = settings.resolved_backup_root

    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _page(*, items: list[dict[str, object]], page: int, page_size: int, total: int):
        return {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": ceil(total / page_size) if total else 0,
        }

    def list_users(self, *, page: int, page_size: int) -> dict[str, object]:
        material_usage = (
            select(
                materials.c.owner_id.label("owner_id"),
                func.count().label("material_count"),
                func.coalesce(func.sum(materials.c.size), 0).label("material_bytes"),
            )
            .group_by(materials.c.owner_id)
            .subquery()
        )
        workspace_usage = (
            select(
                records.c.owner_id.label("owner_id"),
                func.count().label("workspace_count"),
            )
            .where(records.c.collection == "workspaces")
            .group_by(records.c.owner_id)
            .subquery()
        )
        with self.database.session() as session:
            total = int(session.scalar(select(func.count()).select_from(users)) or 0)
            rows = session.execute(
                select(
                    users.c.id,
                    users.c.email,
                    users.c.display_name,
                    users.c.role,
                    users.c.created_at,
                    func.coalesce(material_usage.c.material_count, 0).label("materials"),
                    func.coalesce(material_usage.c.material_bytes, 0).label("material_bytes"),
                    func.coalesce(workspace_usage.c.workspace_count, 0).label("workspaces"),
                )
                .outerjoin(material_usage, material_usage.c.owner_id == users.c.id)
                .outerjoin(workspace_usage, workspace_usage.c.owner_id == users.c.id)
                .order_by(users.c.created_at.desc(), users.c.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        items = [
            {
                "id": row.id,
                "email": row.email,
                "display_name": row.display_name,
                "role": row.role,
                "created_at": self._aware(row.created_at),
                "usage": {
                    "materials": int(row.materials),
                    "material_bytes": int(row.material_bytes),
                    "workspaces": int(row.workspaces),
                },
                "quotas": {
                    "materials": self.settings.material_max_count_per_user,
                    "material_bytes": self.settings.material_max_bytes_per_user,
                    "workspaces": self.settings.max_workspaces_per_user,
                },
            }
            for row in rows
        ]
        return self._page(items=items, page=page, page_size=page_size, total=total)

    def jobs(self) -> dict[str, object]:
        with self.database.session() as session:
            material_row = session.execute(
                select(
                    func.count().label("total"),
                    func.sum(case((materials.c.status == "indexed", 1), else_=0)).label(
                        "completed"
                    ),
                    func.sum(case((materials.c.status == "failed", 1), else_=0)).label("failed"),
                    func.max(materials.c.indexed_at).label("last_activity_at"),
                )
            ).one()
            embedding_row = session.execute(
                select(
                    func.count().label("total"),
                    func.sum(case((material_chunks.c.embedding.is_not(None), 1), else_=0)).label(
                        "completed"
                    ),
                )
            ).one()
        material_total = int(material_row.total or 0)
        material_completed = int(material_row.completed or 0)
        material_failed = int(material_row.failed or 0)
        embedding_total = int(embedding_row.total or 0)
        embedding_completed = int(embedding_row.completed or 0)
        return {
            "observed_at": datetime.now(UTC),
            "items": [
                {
                    "id": "material_index",
                    "status": (
                        "pending"
                        if material_total > material_completed + material_failed
                        else "idle"
                    ),
                    "pending": max(0, material_total - material_completed - material_failed),
                    "completed": material_completed,
                    "failed": material_failed,
                    "total": material_total,
                    "last_activity_at": self._aware(material_row.last_activity_at),
                },
                {
                    "id": "embedding_backfill",
                    "status": "pending" if embedding_total > embedding_completed else "idle",
                    "pending": max(0, embedding_total - embedding_completed),
                    "completed": embedding_completed,
                    "failed": 0,
                    "total": embedding_total,
                    "last_activity_at": self._aware(material_row.last_activity_at),
                },
            ],
        }

    def learning_metrics(
        self,
        *,
        starts_at: datetime,
        ends_at: datetime,
    ) -> dict[str, object]:
        with self.database.session() as session:
            rows = session.execute(
                select(records.c.owner_id, records.c.record_id, records.c.data).where(
                    records.c.collection == "journey_events"
                )
            ).all()
        event_records = [
            (
                str(row.owner_id),
                str(row.record_id),
                row.data.get("events", []),
            )
            for row in rows
        ]
        return learning_journey_metrics(
            event_records,
            starts_at=starts_at,
            ends_at=ends_at,
        )

    def audit(self, *, actor_id: str, action: str, target: str, details: dict) -> None:
        with self.database.session() as session:
            session.execute(
                insert(audit_logs).values(
                    actor_id=actor_id,
                    action=action,
                    target=target,
                    details=details,
                    created_at=datetime.now(UTC),
                )
            )

    def list_audit(self, *, page: int, page_size: int) -> dict[str, object]:
        with self.database.session() as session:
            total = int(session.scalar(select(func.count()).select_from(audit_logs)) or 0)
            rows = session.execute(
                select(audit_logs, users.c.email.label("actor_email"))
                .join(users, users.c.id == audit_logs.c.actor_id)
                .order_by(audit_logs.c.created_at.desc(), audit_logs.c.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
        items = [
            {
                "id": int(row.id),
                "actor_id": row.actor_id,
                "actor_email": row.actor_email,
                "action": row.action,
                "target": row.target,
                "details": dict(row.details),
                "created_at": self._aware(row.created_at),
            }
            for row in rows
        ]
        return self._page(items=items, page=page, page_size=page_size, total=total)

    def create_backup(self, *, actor_id: str) -> ManagedBackup:
        backup = create_managed_backup(self.settings.data_root, self.backup_root)
        try:
            self.audit(
                actor_id=actor_id,
                action="backup.created",
                target=backup.id,
                details={
                    "file_count": backup.file_count,
                    "total_bytes": backup.total_bytes,
                },
            )
        except Exception as error:
            try:
                delete_managed_backup(self.backup_root, backup.id)
            except BackupError as cleanup_error:
                raise BackupError(
                    "Backup audit failed and archive cleanup could not be confirmed"
                ) from cleanup_error
            raise BackupError("Backup audit failed; the created archive was removed") from error
        return backup

    def list_backups(self) -> list[ManagedBackup]:
        return list_managed_backups(self.backup_root)

    def validate_restore(
        self,
        backup_id: str,
        *,
        confirmation: str,
        actor_id: str,
    ) -> ManagedBackup:
        if confirmation != f"RESTORE {backup_id}":
            raise RestoreConfirmationError("Exact restore confirmation is required")
        backup = validate_managed_backup(self.backup_root, backup_id)
        self.audit(
            actor_id=actor_id,
            action="backup.restore_validated",
            target=backup.id,
            details={"file_count": backup.file_count, "total_bytes": backup.total_bytes},
        )
        return backup


def ensure_admin(
    identity: IdentityService,
    *,
    email: str,
    password: str,
    display_name: str,
) -> AdminBootstrapResult:
    """Create an administrator or promote and reset an existing account."""

    user, created = identity.create_or_update_admin(
        email=email,
        password=password,
        display_name=display_name,
    )
    return AdminBootstrapResult(user=user, created=created)
