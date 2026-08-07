"""Administrator role and live authorization tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from refineq.api.dependencies import require_admin
from refineq.database.engine import Database
from refineq.identity.models import User
from refineq.identity.service import IdentityService, InvalidTokenError
from refineq.operations.admin import ensure_admin


def _identity(tmp_path) -> IdentityService:
    database = Database(f"sqlite+pysqlite:///{(tmp_path / 'admin.sqlite3').as_posix()}")
    database.initialize()
    return IdentityService(database)


def test_newly_registered_accounts_are_learners(tmp_path) -> None:
    identity = _identity(tmp_path)

    user = identity.register(
        email="learner@example.com",
        password="correct-horse-battery-staple",
        display_name="Learner",
    )

    assert user.role == "learner"


def test_admin_dependency_rejects_learners_and_accepts_admins() -> None:
    learner = User(
        id="learner",
        email="learner@example.com",
        display_name="Learner",
        role="learner",
        created_at=datetime.now(UTC),
    )
    admin = learner.model_copy(update={"id": "admin", "role": "admin"})

    with pytest.raises(HTTPException) as denied:
        require_admin(learner)
    assert denied.value.status_code == 403
    assert require_admin(admin) == admin


def test_admin_promotion_with_password_change_revokes_existing_token(tmp_path) -> None:
    identity = _identity(tmp_path)
    learner = identity.register(
        email="owner@example.com",
        password="correct-horse-battery-staple",
        display_name="Owner",
    )
    token = identity.issue_token(learner)

    promoted = ensure_admin(
        identity,
        email="owner@example.com",
        password="new-correct-horse-battery",
        display_name="QingJ",
    )

    assert promoted.created is False
    assert promoted.user.role == "admin"
    with pytest.raises(InvalidTokenError):
        identity.verify_token(token)
    assert identity.verify_token(identity.issue_token(promoted.user)).role == "admin"


def test_admin_bootstrap_is_idempotent_and_resets_the_requested_password(tmp_path) -> None:
    identity = _identity(tmp_path)

    first = ensure_admin(
        identity,
        email="qingj1314@163.com",
        password="first-correct-horse-password",
        display_name="QingJ01",
    )
    second = ensure_admin(
        identity,
        email="qingj1314@163.com",
        password="second-correct-horse-password",
        display_name="QingJ01",
    )

    assert first.created is True
    assert second.created is False
    assert first.user.id == second.user.id
    assert (
        identity.authenticate(
            email="qingj1314@163.com",
            password="second-correct-horse-password",
        ).role
        == "admin"
    )
