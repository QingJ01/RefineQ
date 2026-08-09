"""Administrator role and live authorization tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.api.dependencies import require_admin
from refineq.config import Settings
from refineq.database.engine import Database
from refineq.identity.models import User
from refineq.identity.service import IdentityService, InvalidTokenError
from refineq.learning.events import build_journey_event
from refineq.operations.admin import ensure_admin
from refineq.workspaces.service import WorkspaceResolveRequest


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


def test_admin_operations_are_paginated_guarded_and_audited(tmp_path) -> None:
    settings = Settings(
        data_root=tmp_path / "data",
        material_max_count_per_user=7,
        material_max_bytes_per_user=1024,
        max_workspaces_per_user=5,
        _env_file=None,
    )
    app = create_app(settings)
    learner = app.state.identity.register(
        email="operations-learner@example.com",
        password="correct-horse-battery-staple",
        display_name="Learner",
    )
    app.state.identity.register(
        email="second-learner@example.com",
        password="correct-horse-battery-staple",
        display_name="Second learner",
    )
    admin = ensure_admin(
        app.state.identity,
        email="operations-admin@example.com",
        password="correct-horse-battery-staple",
        display_name="Admin",
    ).user
    app.state.workspaces.create(
        learner.id,
        "workspace-operations",
        title="Operations",
        subject="Systems",
        goal="Inspect operations",
        topics=["jobs"],
        keywords=["jobs"],
        routing_summary="Operations workspace",
    )
    app.state.knowledge.add_document(
        owner_id=learner.id,
        project_id="workspace-operations",
        material_id="material-operations",
        filename="operations.txt",
        text="material indexing status",
        size=24,
    )
    learner_headers = {"Authorization": f"Bearer {app.state.identity.issue_token(learner)}"}
    admin_headers = {"Authorization": f"Bearer {app.state.identity.issue_token(admin)}"}

    with TestClient(app) as client:
        for path in ("/admin/users", "/admin/jobs", "/admin/audit", "/admin/backups"):
            assert client.get(path, headers=learner_headers).status_code == 403
        assert client.post("/admin/backups", headers=learner_headers).status_code == 403

        users_response = client.get(
            "/admin/users?page=1&page_size=2",
            headers=admin_headers,
        )
        users_response_page2 = client.get(
            "/admin/users?page=2&page_size=2",
            headers=admin_headers,
        )
        jobs_response = client.get("/admin/jobs", headers=admin_headers)
        created_response = client.post("/admin/backups", headers=admin_headers)
        backup_id = created_response.json()["id"]
        listed_response = client.get("/admin/backups", headers=admin_headers)
        refused_restore = client.post(
            f"/admin/backups/{backup_id}/restore-validation",
            headers=admin_headers,
            json={"confirmation": "RESTORE something-else"},
        )
        validated_restore = client.post(
            f"/admin/backups/{backup_id}/restore-validation",
            headers=admin_headers,
            json={"confirmation": f"RESTORE {backup_id}"},
        )
        audit_response = client.get(
            "/admin/audit?page=1&page_size=1",
            headers=admin_headers,
        )
        invalid_id = client.post(
            "/admin/backups/not-a-managed-backup/restore-validation",
            headers=admin_headers,
            json={"confirmation": "RESTORE not-a-managed-backup"},
        )

    assert users_response.status_code == 200
    users_page = users_response.json()
    assert users_page["total"] == 3
    assert users_page["page"] == 1
    assert users_page["page_size"] == 2
    assert users_page["pages"] == 2
    all_user_items = users_page["items"] + users_response_page2.json()["items"]
    learner_summary = next(item for item in all_user_items if item["id"] == learner.id)
    assert learner_summary["usage"] == {
        "materials": 1,
        "material_bytes": 24,
        "workspaces": 1,
    }
    assert learner_summary["quotas"] == {
        "materials": 7,
        "material_bytes": 1024,
        "workspaces": 5,
    }
    assert jobs_response.status_code == 200
    assert [item["id"] for item in jobs_response.json()["items"]] == [
        "material_index",
        "embedding_backfill",
    ]
    assert created_response.status_code == 201
    assert backup_id.startswith("backup_")
    assert listed_response.json()["items"][0]["id"] == backup_id
    assert refused_restore.status_code == 409
    assert refused_restore.json()["error"]["code"] == "restore_confirmation_required"
    assert validated_restore.status_code == 200
    assert validated_restore.json()["status"] == "validated"
    assert audit_response.status_code == 200
    assert audit_response.json()["total"] >= 2
    assert audit_response.json()["items"][0]["action"] == "backup.restore_validated"
    assert invalid_id.status_code == 404


def test_learning_metrics_are_admin_only_and_derived_from_internal_events(tmp_path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    learner = app.state.identity.register(
        email="metrics-learner@example.com",
        password="correct-horse-battery-staple",
        display_name="Metrics Learner",
    )
    admin = ensure_admin(
        app.state.identity,
        email="metrics-admin@example.com",
        password="correct-horse-battery-staple",
        display_name="Metrics Admin",
    ).user
    now = datetime.now(UTC).replace(microsecond=0)
    workspace = app.state.workspace_service.resolve(
        learner.id,
        WorkspaceResolveRequest(intent="Prepare calculus"),
        now=now,
    ).workspace

    for name, minute in (("grounded_grade_created", 10), ("grounded_grade_shown", 11)):
        app.state.journey_events.append(
            learner.id,
            workspace.id,
            build_journey_event(
                workspace_id=workspace.id,
                name=name,
                idempotency_key="attempt-1",
                occurred_at=now + timedelta(minutes=minute),
                ref_id="attempt-1",
            ),
        )
    learner_headers = {"Authorization": f"Bearer {app.state.identity.issue_token(learner)}"}
    admin_headers = {"Authorization": f"Bearer {app.state.identity.issue_token(admin)}"}
    params = {
        "starts_at": (now - timedelta(minutes=1)).isoformat(),
        "ends_at": (now + timedelta(days=7)).isoformat(),
    }

    with TestClient(app) as client:
        forbidden = client.get("/admin/metrics/learning", headers=learner_headers, params=params)
        response = client.get("/admin/metrics/learning", headers=admin_headers, params=params)

    assert forbidden.status_code == 403
    assert response.status_code == 200
    assert response.json()["active_learners"] == 1
    assert response.json()["grounded_loop_completers"] == 1
    assert response.json()["grounded_loop_completion_rate"] == 1.0
    assert response.json()["intent_to_grounded_grade_seconds"] == {
        "sample_size": 1,
        "p50": 600.0,
        "p90": 600.0,
    }


@pytest.mark.parametrize(
    ("filename", "payload"),
    [
        ("broken.json", b"{not-json"),
        ("broken.sqlite3", b"not-a-sqlite-database"),
    ],
)
def test_admin_backup_failures_do_not_expose_server_paths(
    tmp_path,
    filename: str,
    payload: bytes,
) -> None:
    settings = Settings(data_root=tmp_path / "private-runtime", _env_file=None)
    app = create_app(settings)
    admin = ensure_admin(
        app.state.identity,
        email="safe-errors-admin@example.com",
        password="correct-horse-battery-staple",
        display_name="Admin",
    ).user
    settings.data_root.mkdir(parents=True, exist_ok=True)
    (settings.data_root / filename).write_bytes(payload)
    headers = {"Authorization": f"Bearer {app.state.identity.issue_token(admin)}"}

    with TestClient(app) as client:
        response = client.post("/admin/backups", headers=headers)

    assert response.status_code == 503
    assert response.json()["error"] == {
        "code": "backup_creation_failed",
        "message": "Backup could not be created safely.",
    }
    assert str(settings.data_root) not in response.text
    assert str(app.state.admin_operations.backup_root) not in response.text
