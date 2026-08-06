"""Integration coverage for local authentication and owner isolation."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.config import Settings
from refineq.identity.service import IdentityService, TokenExpiredError
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
    auth_file = tmp_path / "data" / "system" / "auth.json"
    persisted = json.loads(auth_file.read_text(encoding="utf-8"))
    serialized = auth_file.read_text(encoding="utf-8")
    assert "correct-horse-battery-staple" not in serialized
    assert persisted["schema_version"] == 1
    assert persisted["users"]["learner@example.com"]["password_hash"].startswith("$2")


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


def test_two_users_cannot_read_the_same_project_id(tmp_path: Path) -> None:
    app = _app(tmp_path)

    with TestClient(app) as client:
        alice = _register(client, "alice@example.com")
        bob = _register(client, "bob@example.com")

    app.state.projects.create(alice["user"]["id"], "shared", name="Alice project")

    with pytest.raises(RecordNotFoundError):
        app.state.projects.get(bob["user"]["id"], "shared")
