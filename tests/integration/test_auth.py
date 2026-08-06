"""Integration coverage for local authentication and owner isolation."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.config import Settings
from refineq.identity.service import IdentityService, InvalidTokenError, TokenExpiredError
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
