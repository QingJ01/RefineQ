"""Integration coverage for local authentication and owner isolation."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from refineq.api.app import create_app
from refineq.api.routers.projects import ProjectCreateRequest, create_project
from refineq.config import Settings
from refineq.database.schema import records, system_settings
from refineq.identity.service import (
    AccountDeletionError,
    IdentityService,
    InvalidTokenError,
    TokenExpiredError,
)
from refineq.storage.json_store import RecordNotFoundError


def _app(tmp_path: Path):
    return create_app(Settings(data_root=tmp_path / "data", _env_file=None))


def _register(client: TestClient, email: str) -> dict[str, object]:
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "display_name": email.split("@", 1)[0],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_first_user_registration_hashes_the_password(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as client:
        payload = _register(client, "learner@example.com")

    assert payload["token_type"] == "bearer"
    assert payload["user"]["email"] == "learner@example.com"
    assert payload["user"]["role"] == "learner"
    database_file = tmp_path / "data" / "system" / "refineq.sqlite3"
    assert "correct-horse-battery-staple" not in database_file.read_bytes().decode(
        "utf-8", errors="ignore"
    )


def test_login_and_authenticated_profile(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as client:
        registered = _register(client, "learner@example.com")
        login = client.post(
            "/auth/login",
            json={
                "email": "LEARNER@example.com",
                "password": "correct-horse-battery-staple",
            },
        )
        profile = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        )

    assert login.status_code == 200
    assert profile.status_code == 200
    assert profile.json() == registered["user"]


def test_invalid_login_uses_a_specific_error_code(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        response = client.post(
            "/auth/login",
            json={"email": "missing@example.com", "password": "wrong-password"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_unauthorized_access_uses_a_stable_error_code(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_expired_token_is_rejected(tmp_path: Path) -> None:
    identity = IdentityService(tmp_path / "data", token_ttl=timedelta(minutes=5))
    user = identity.register(
        email="learner@example.com",
        password="correct-horse-battery-staple",
        display_name="Learner",
    )
    issued_at = datetime(2026, 8, 6, 10, 0, tzinfo=UTC)
    token = identity.issue_token(user, now=issued_at)

    with pytest.raises(TokenExpiredError):
        identity.verify_token(token, now=issued_at + timedelta(minutes=6))


def test_tampered_token_is_rejected(tmp_path: Path) -> None:
    identity = IdentityService(tmp_path / "data")
    user = identity.register(
        email="learner@example.com",
        password="correct-horse-battery-staple",
        display_name="Learner",
    )
    token = identity.issue_token(user)
    replacement = "a" if token[-1] != "a" else "b"

    with pytest.raises(InvalidTokenError):
        identity.verify_token(f"{token[:-1]}{replacement}")


def test_two_users_cannot_read_the_same_project_id(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as client:
        alice = _register(client, "alice@example.com")
        bob = _register(client, "bob@example.com")

    app.state.projects.create(alice["user"]["id"], "shared", name="Alice project")

    with pytest.raises(RecordNotFoundError):
        app.state.projects.get(bob["user"]["id"], "shared")


def test_authentication_burst_is_rate_limited_by_client(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            data_root=tmp_path / "data",
            auth_rate_limit_requests=2,
            mutation_rate_limit_requests=100,
            _env_file=None,
        )
    )

    with TestClient(app) as client:
        responses = [
            client.post(
                "/auth/login",
                json={"email": "missing@example.com", "password": "wrong-password"},
            )
            for _ in range(3)
        ]

    assert [response.status_code for response in responses] == [401, 401, 429]
    assert responses[-1].json()["error"]["code"] == "rate_limit_exceeded"
    assert int(responses[-1].headers["Retry-After"]) >= 1


def test_authenticated_mutation_burst_is_rate_limited(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            data_root=tmp_path / "data",
            auth_rate_limit_requests=10,
            mutation_rate_limit_requests=2,
            _env_file=None,
        )
    )

    with TestClient(app) as client:
        registered = _register(client, "limited@example.com")
        headers = {"Authorization": f"Bearer {registered['access_token']}"}
        responses = [
            client.post("/projects", headers=headers, json={"name": f"Project {index}"})
            for index in range(3)
        ]

    assert [response.status_code for response in responses] == [201, 201, 429]
    assert responses[-1].json()["error"]["code"] == "rate_limit_exceeded"


def test_concurrent_project_creates_cannot_cross_owner_quota(tmp_path: Path, monkeypatch) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", max_projects_per_user=1, _env_file=None))
    user = app.state.identity.register(
        email="project-quota@example.com",
        password="correct-horse-battery-staple",
        display_name="Learner",
    )
    original_create = app.state.projects.create

    def slow_create(*args, **kwargs):
        time.sleep(0.05)
        return original_create(*args, **kwargs)

    monkeypatch.setattr(app.state.projects, "create", slow_create)

    def invoke(index: int) -> int:
        try:
            create_project(
                ProjectCreateRequest(name=f"Project {index}"),
                type("Request", (), {"app": app})(),
                user,
            )
        except Exception as error:
            return getattr(error, "status_code", 500)
        return 201

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = sorted(executor.map(invoke, range(2)))

    assert statuses == [201, 409]
    assert app.state.projects.count(user.id) == 1


def test_password_limits_are_measured_in_utf8_bytes(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/auth/register",
            json={
                "email": "unicode-password@example.com",
                "password": "密" * 30,
                "display_name": "Learner",
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_multibyte_password_at_twelve_bytes_is_accepted(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        response = client.post(
            "/auth/register",
            json={
                "email": "unicode-minimum@example.com",
                "password": "密碼安全",
                "display_name": "Learner",
            },
        )

    assert response.status_code == 201


def test_blank_display_name_is_a_validation_error_not_a_server_error(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path), raise_server_exceptions=False) as client:
        response = client.post(
            "/auth/register",
            json={
                "email": "blank-name@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "   ",
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_password_reset_is_one_time_and_does_not_expose_account_lookup(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            data_root=tmp_path / "data",
            password_reset_expose_token=True,
            _env_file=None,
        )
    )

    with TestClient(app) as client:
        _register(client, "reset@example.com")
        missing = client.post(
            "/auth/password-reset/request",
            json={"email": "missing@example.com"},
        )
        requested = client.post(
            "/auth/password-reset/request",
            json={"email": "reset@example.com"},
        )
        assert missing.status_code == 202
        assert missing.json()["accepted"] is True
        assert requested.status_code == 202
        assert requested.json()["accepted"] is True
        token = requested.json()["reset_token"]
        assert token

        reset = client.post(
            "/auth/password-reset/complete",
            json={"token": token, "password": "a-brand-new-secure-password"},
        )
        reused = client.post(
            "/auth/password-reset/complete",
            json={"token": token, "password": "another-secure-password"},
        )
        login = client.post(
            "/auth/login",
            json={"email": "reset@example.com", "password": "a-brand-new-secure-password"},
        )

    assert reset.status_code == 204
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "invalid_reset_token"
    assert login.status_code == 200
    database_file = tmp_path / "data" / "system" / "refineq.sqlite3"
    assert token not in database_file.read_bytes().decode("utf-8", errors="ignore")


def test_password_reset_token_is_hidden_by_default_for_every_email(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as client:
        _register(client, "hidden-reset@example.com")
        existing = client.post(
            "/auth/password-reset/request",
            json={"email": "hidden-reset@example.com"},
        )
        missing = client.post(
            "/auth/password-reset/request",
            json={"email": "missing-reset@example.com"},
        )

    assert existing.status_code == 202
    assert missing.status_code == 202
    assert existing.json() == missing.json() == {"accepted": True, "reset_token": None}


def test_password_reset_revokes_access_tokens_issued_before_password_change(
    tmp_path: Path,
) -> None:
    app = create_app(
        Settings(
            data_root=tmp_path / "data",
            password_reset_expose_token=True,
            _env_file=None,
        )
    )

    with TestClient(app) as client:
        registered = _register(client, "revoked-after-reset@example.com")
        old_token = registered["access_token"]
        reset_token = client.post(
            "/auth/password-reset/request",
            json={"email": "revoked-after-reset@example.com"},
        ).json()["reset_token"]
        reset = client.post(
            "/auth/password-reset/complete",
            json={"token": reset_token, "password": "a-brand-new-secure-password"},
        )
        stale = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {old_token}"},
        )

    assert reset.status_code == 204
    assert stale.status_code == 401
    assert stale.json()["error"]["code"] == "unauthorized"


def test_password_reset_token_expires(tmp_path: Path) -> None:
    app = _app(tmp_path)
    user = app.state.identity.register(
        email="expired-reset@example.com",
        password="correct-horse-battery-staple",
        display_name="Learner",
    )
    issued_at = datetime(2026, 8, 7, 10, 0, tzinfo=UTC)
    token = app.state.identity.request_password_reset(
        user.email,
        now=issued_at,
        ttl=timedelta(minutes=5),
    )

    with pytest.raises(ValueError, match="reset token"):
        app.state.identity.reset_password(
            token,
            "a-brand-new-secure-password",
            now=issued_at + timedelta(minutes=6),
        )


def test_profile_and_password_can_be_updated_with_current_password(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as client:
        registered = _register(client, "account-profile@example.com")
        token = registered["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        profile = client.patch(
            "/auth/profile",
            headers=headers,
            json={"display_name": "Focused Learner"},
        )
        wrong_password = client.put(
            "/auth/password",
            headers=headers,
            json={
                "current_password": "not-the-current-password",
                "new_password": "a-brand-new-secure-password",
            },
        )
        changed = client.put(
            "/auth/password",
            headers=headers,
            json={
                "current_password": "correct-horse-battery-staple",
                "new_password": "a-brand-new-secure-password",
            },
        )
        stale = client.get("/auth/me", headers=headers)
        old_login = client.post(
            "/auth/login",
            json={
                "email": "account-profile@example.com",
                "password": "correct-horse-battery-staple",
            },
        )
        new_login = client.post(
            "/auth/login",
            json={
                "email": "account-profile@example.com",
                "password": "a-brand-new-secure-password",
            },
        )

    assert profile.status_code == 200
    assert profile.json()["display_name"] == "Focused Learner"
    assert wrong_password.status_code == 401
    assert wrong_password.json()["error"]["code"] == "invalid_credentials"
    assert changed.status_code == 204
    assert stale.status_code == 401
    assert old_login.status_code == 401
    assert new_login.status_code == 200
    assert new_login.json()["user"]["display_name"] == "Focused Learner"


def test_logout_all_revokes_every_existing_token(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as client:
        registered = _register(client, "sessions@example.com")
        first_token = registered["access_token"]
        second_token = client.post(
            "/auth/login",
            json={
                "email": "sessions@example.com",
                "password": "correct-horse-battery-staple",
            },
        ).json()["access_token"]
        revoked = client.delete(
            "/auth/sessions",
            headers={"Authorization": f"Bearer {first_token}"},
        )
        first_stale = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {first_token}"},
        )
        second_stale = client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {second_token}"},
        )
        fresh_login = client.post(
            "/auth/login",
            json={
                "email": "sessions@example.com",
                "password": "correct-horse-battery-staple",
            },
        )

    assert revoked.status_code == 204
    assert first_stale.status_code == 401
    assert second_stale.status_code == 401
    assert fresh_login.status_code == 200


def test_login_token_is_bound_to_the_password_snapshot_that_authenticated_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    identity = IdentityService(tmp_path / "data")
    identity.register(
        email="login-race@example.com",
        password="correct-horse-battery-staple",
        display_name="Learner",
    )
    entered = Event()
    release = Event()
    original_encode = identity._encode_token

    def delayed_encode(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original_encode(*args, **kwargs)

    monkeypatch.setattr(identity, "_encode_token", delayed_encode)
    with ThreadPoolExecutor(max_workers=2) as executor:
        login_future = executor.submit(
            identity.authenticate_with_token,
            email="login-race@example.com",
            password="correct-horse-battery-staple",
        )
        assert entered.wait(timeout=5)
        user = identity.authenticate(
            email="login-race@example.com",
            password="correct-horse-battery-staple",
        )
        identity.change_password(
            user.id,
            current_password="correct-horse-battery-staple",
            new_password="a-brand-new-secure-password",
        )
        release.set()
        _, stale_token = login_future.result(timeout=5)

    with pytest.raises(InvalidTokenError):
        identity.verify_token(stale_token)


def test_logout_all_increment_is_atomic_across_service_instances(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _app(tmp_path)
    user = app.state.identity.register(
        email="session-version-race@example.com",
        password="correct-horse-battery-staple",
        display_name="Learner",
    )
    first = IdentityService(app.state.database)
    second = IdentityService(app.state.database)
    barrier = Barrier(2)

    def synchronize(service: IdentityService):
        original = service._session_version

        def read_together(session, user_id):
            value = original(session, user_id)
            barrier.wait(timeout=5)
            return value

        monkeypatch.setattr(service, "_session_version", read_together)

    synchronize(first)
    synchronize(second)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(first.revoke_sessions, user.id),
            executor.submit(second.revoke_sessions, user.id),
        ]
        for future in futures:
            future.result(timeout=5)

    with app.state.database.session() as session:
        version = session.scalar(
            select(system_settings.c.value).where(
                system_settings.c.key == f"user_session_version:{user.id}"
            )
        )
    assert version == "2"


def test_account_export_contains_only_the_authenticated_owner_data(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as client:
        alice = _register(client, "export-alice@example.com")
        bob = _register(client, "export-bob@example.com")
        alice_headers = {"Authorization": f"Bearer {alice['access_token']}"}
        bob_headers = {"Authorization": f"Bearer {bob['access_token']}"}
        alice_workspace = client.post(
            "/workspaces/resolve",
            headers=alice_headers,
            json={"intent": "Alice private calculus goal"},
        ).json()["workspace"]
        bob_workspace = client.post(
            "/workspaces/resolve",
            headers=bob_headers,
            json={"intent": "Bob private physics goal"},
        ).json()["workspace"]

        exported = client.get("/auth/export", headers=alice_headers)

    assert exported.status_code == 200
    assert exported.headers["content-disposition"].startswith("attachment;")
    body = exported.json()
    assert body["user"]["email"] == "export-alice@example.com"
    serialized = exported.text
    assert alice_workspace["id"] in serialized
    assert bob_workspace["id"] not in serialized
    assert "export-bob@example.com" not in serialized
    assert all(record["owner_id"] == alice["user"]["id"] for record in body["records"])


def test_account_deletion_is_fail_safe_when_object_cleanup_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _app(tmp_path)
    with TestClient(app, raise_server_exceptions=False) as client:
        registered = _register(client, "delete-fails@example.com")
        owner_id = registered["user"]["id"]
        token = registered["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        entries = []
        for index in range(2):
            stored = app.state.object_storage.put(
                owner_id=owner_id,
                workspace_id="workspace-delete-test",
                material_id=f"material-delete-{index}",
                filename=f"material-{index}.txt",
                payload=f"payload-{index}".encode(),
            )
            entries.append({
                "key": stored.key,
                "workspace_id": "workspace-delete-test",
                "material_id": f"material-delete-{index}",
                "filename": f"material-{index}.txt",
            })
        monkeypatch.setattr(
            app.state.identity,
            "account_storage_objects",
            lambda requested_owner: entries if requested_owner == owner_id else [],
            raising=False,
        )
        original_delete = app.state.object_storage.delete
        deleted_keys: list[str] = []

        def fail_after_first(storage_key: str) -> None:
            if deleted_keys:
                raise RuntimeError(f"cannot delete {storage_key}")
            original_delete(storage_key)
            deleted_keys.append(storage_key)

        monkeypatch.setattr(app.state.object_storage, "delete", fail_after_first)
        failed = client.request(
            "DELETE",
            "/auth/account",
            headers=headers,
            json={
                "current_password": "correct-horse-battery-staple",
                "confirmation": "delete-fails@example.com",
            },
        )
        still_authenticated = client.get("/auth/me", headers=headers)

    assert failed.status_code == 503
    assert failed.json()["error"]["code"] == "account_deletion_failed"
    assert still_authenticated.status_code == 200
    assert app.state.object_storage.get(entries[0]["key"]) == b"payload-0"
    assert app.state.object_storage.get(entries[1]["key"]) == b"payload-1"


def test_account_deletion_preflight_blocks_before_removing_objects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _app(tmp_path)
    delete_calls: list[str] = []

    def blocked(*args, **kwargs):
        del args, kwargs
        raise AccountDeletionError("Transfer platform integration ownership first")

    monkeypatch.setattr(
        app.state.identity,
        "preflight_account_deletion",
        blocked,
        raising=False,
    )
    monkeypatch.setattr(
        app.state.object_storage,
        "delete",
        lambda key: delete_calls.append(key),
    )

    with TestClient(app) as client:
        registered = _register(client, "delete-blocked@example.com")
        response = client.request(
            "DELETE",
            "/auth/account",
            headers={"Authorization": f"Bearer {registered['access_token']}"},
            json={
                "current_password": "correct-horse-battery-staple",
                "confirmation": "delete-blocked@example.com",
            },
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_deletion_blocked"
    assert delete_calls == []


def test_pending_account_deletion_is_recovered_after_process_interruption(
    tmp_path: Path,
) -> None:
    settings = Settings(data_root=tmp_path / "data", _env_file=None)
    app = create_app(settings)
    storage_key = ""

    with TestClient(app) as client:
        registered = _register(client, "delete-recovery@example.com")
        headers = {"Authorization": f"Bearer {registered['access_token']}"}
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study durable deletion"},
        ).json()["workspace"]["id"]
        material = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files={"files": ("notes.txt", b"Recover me", "text/plain")},
        ).json()[0]
        storage_key = app.state.knowledge.get_material_storage_key(
            owner_id=registered["user"]["id"],
            project_id=workspace_id,
            material_id=material["id"],
        )

        app.state.account_deletions.prepare(
            registered["user"]["id"],
            current_password="correct-horse-battery-staple",
        )
        app.state.object_storage.delete(storage_key)

    recovered_app = create_app(settings)
    with TestClient(recovered_app) as recovered_client:
        login = recovered_client.post(
            "/auth/login",
            json={
                "email": "delete-recovery@example.com",
                "password": "correct-horse-battery-staple",
            },
        )

    assert login.status_code == 200
    assert recovered_app.state.object_storage.get(storage_key) == b"Recover me"
    recovery_root = settings.data_root / "recovery" / "account-deletions"
    assert not recovery_root.exists() or not any(path.is_dir() for path in recovery_root.iterdir())


def test_live_account_deletion_is_not_recovered_by_another_app_instance(
    tmp_path: Path,
) -> None:
    settings = Settings(data_root=tmp_path / "data", _env_file=None)
    active_app = create_app(settings)
    user = active_app.state.identity.register(
        email="active-delete@example.com",
        password="correct-horse-battery-staple",
        display_name="Learner",
    )
    stored = active_app.state.object_storage.put(
        owner_id=user.id,
        workspace_id="workspace-active",
        material_id="material-active",
        filename="active.txt",
        payload=b"active deletion",
    )
    active_app.state.knowledge.add_document(
        owner_id=user.id,
        project_id="workspace-active",
        material_id="material-active",
        filename="active.txt",
        text="active deletion",
        size=len(b"active deletion"),
        storage_key=stored.key,
    )
    pending = active_app.state.account_deletions.prepare(
        user.id,
        current_password="correct-horse-battery-staple",
    )
    active_app.state.object_storage.delete(stored.key)

    second_app = create_app(settings)
    try:
        assert active_app.state.identity.account_deletion_state(user.id) == (
            True,
            pending.deletion_id,
        )
        with pytest.raises(FileNotFoundError):
            active_app.state.object_storage.get(stored.key)
    finally:
        second_app.state.account_deletions.close()
        second_app.state.material_deletions.close()
        second_app.state.database.close()
        active_app.state.account_deletions.rollback(pending)
        active_app.state.database.close()

    assert active_app.state.object_storage.get(stored.key) == b"active deletion"


def test_account_and_material_deletions_share_one_cross_process_lease(tmp_path: Path) -> None:
    app = _app(tmp_path)
    user = app.state.identity.register(
        email="shared-delete-lease@example.com",
        password="correct-horse-battery-staple",
        display_name="Learner",
    )
    stored = app.state.object_storage.put(
        owner_id=user.id,
        workspace_id="workspace-shared",
        material_id="material-shared",
        filename="shared.txt",
        payload=b"shared lease",
    )
    app.state.knowledge.add_document(
        owner_id=user.id,
        project_id="workspace-shared",
        material_id="material-shared",
        filename="shared.txt",
        text="shared lease",
        size=12,
        storage_key=stored.key,
    )
    pending = app.state.account_deletions.prepare(
        user.id,
        current_password="correct-horse-battery-staple",
    )

    try:
        with pytest.raises(RuntimeError, match="material object mutation"):
            app.state.material_deletions.prepare(
                owner_id=user.id,
                project_id="workspace-shared",
                material_ids=["material-shared"],
            )
    finally:
        app.state.account_deletions.rollback(pending)
        app.state.database.close()


def test_recovery_removes_pre_manifest_crash_directories(tmp_path: Path) -> None:
    settings = Settings(data_root=tmp_path / "data", _env_file=None)
    account_orphan = settings.data_root / "recovery" / "account-deletions" / "orphan"
    material_orphan = settings.data_root / "recovery" / "material-deletions" / "orphan"
    account_orphan.mkdir(parents=True)
    material_orphan.mkdir(parents=True)
    (material_orphan / "000000.bin").write_bytes(b"not yet destructive")

    app = create_app(settings)
    try:
        assert not account_orphan.exists()
        assert not material_orphan.exists()
    finally:
        app.state.account_deletions.close()
        app.state.material_deletions.close()
        app.state.database.close()


def test_initial_account_manifest_failure_releases_the_shared_lease(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = _app(tmp_path)
    user = app.state.identity.register(
        email="manifest-failure@example.com",
        password="correct-horse-battery-staple",
        display_name="Learner",
    )
    original = app.state.account_deletions._write_manifest

    def fail_manifest(*args, **kwargs):
        del args, kwargs
        raise OSError("disk full")

    monkeypatch.setattr(
        app.state.account_deletions,
        "_write_manifest",
        fail_manifest,
    )

    with pytest.raises(OSError, match="disk full"):
        app.state.account_deletions.prepare(
            user.id,
            current_password="correct-horse-battery-staple",
        )

    monkeypatch.setattr(app.state.account_deletions, "_write_manifest", original)
    pending = app.state.account_deletions.prepare(
        user.id,
        current_password="correct-horse-battery-staple",
    )
    app.state.account_deletions.rollback(pending)
    app.state.database.close()


def test_account_deletion_fence_rejects_a_late_material_write(tmp_path: Path) -> None:
    from refineq.database.owner_state import OwnerWriteBlockedError
    from refineq.knowledge.index import MaterialDocument

    app = _app(tmp_path)
    user = app.state.identity.register(
        email="delete-write-race@example.com",
        password="correct-horse-battery-staple",
        display_name="Learner",
    )
    stored = app.state.object_storage.put(
        owner_id=user.id,
        workspace_id="workspace-race",
        material_id="material-race",
        filename="race.txt",
        payload=b"late material",
    )
    deletion_id = "deletion_race"

    app.state.identity.begin_account_deletion(
        user.id,
        current_password="correct-horse-battery-staple",
        deletion_id=deletion_id,
    )
    with pytest.raises(OwnerWriteBlockedError):
        app.state.knowledge.add_documents_with_quota(
            owner_id=user.id,
            documents=[
                MaterialDocument(
                    project_id="workspace-race",
                    material_id="material-race",
                    filename="race.txt",
                    text="late material",
                    size=13,
                    storage_key=stored.key,
                )
            ],
            max_count=10,
            max_bytes=1_000,
        )
    stored.rollback()
    app.state.identity.delete_account(
        user.id,
        current_password="correct-horse-battery-staple",
        deletion_id=deletion_id,
    )

    with pytest.raises(FileNotFoundError):
        app.state.object_storage.get(stored.key)
    assert app.state.knowledge.list_materials(
        owner_id=user.id,
        project_id="workspace-race",
    ) == []


def test_account_deletion_removes_identity_and_owner_records(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as client:
        registered = _register(client, "delete-account@example.com")
        owner_id = registered["user"]["id"]
        token = registered["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Data that must be deleted"},
        )
        deleted = client.request(
            "DELETE",
            "/auth/account",
            headers=headers,
            json={
                "current_password": "correct-horse-battery-staple",
                "confirmation": "delete-account@example.com",
            },
        )
        stale = client.get("/auth/me", headers=headers)
        login = client.post(
            "/auth/login",
            json={
                "email": "delete-account@example.com",
                "password": "correct-horse-battery-staple",
            },
        )

    with app.state.database.session() as session:
        remaining = session.scalar(
            select(func.count()).select_from(records).where(records.c.owner_id == owner_id)
        )
    assert deleted.status_code == 204
    assert stale.status_code == 401
    assert login.status_code == 401
    assert remaining == 0
