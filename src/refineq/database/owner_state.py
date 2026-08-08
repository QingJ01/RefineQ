"""Database-level fencing for writes that belong to one account."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from refineq.database.engine import Database
from refineq.database.schema import users


class OwnerWriteBlockedError(RuntimeError):
    """Raised when an owner was removed or is inside a deletion transaction."""


def lock_writable_owner(session: Session, database: Database, owner_id: str) -> None:
    """Serialize owner writes with account deletion and reject late mutations."""

    if database.is_postgresql:
        row = session.execute(
            select(users.c.deletion_id).where(users.c.id == owner_id).with_for_update()
        ).one_or_none()
    else:
        changed = session.execute(
            update(users).where(users.c.id == owner_id).values(updated_at=users.c.updated_at)
        )
        row = (
            session.execute(select(users.c.deletion_id).where(users.c.id == owner_id)).one_or_none()
            if changed.rowcount == 1
            else None
        )
    if row is None or row.deletion_id is not None:
        raise OwnerWriteBlockedError("Account is unavailable for new writes")
