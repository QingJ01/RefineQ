"""Admin-only platform integration API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.config import Settings
from refineq.operations.admin import ensure_admin


def _tokens(tmp_path):
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    learner = app.state.identity.register(
        email="learner@example.com",
        password="correct-horse-battery-staple",
        display_name="Learner",
    )
    admin = ensure_admin(
        app.state.identity,
        email="admin@example.com",
        password="correct-horse-battery-staple",
        display_name="Admin",
    ).user
    return app, app.state.identity.issue_token(learner), app.state.identity.issue_token(admin)


def test_only_admins_can_read_or_change_platform_integrations(tmp_path) -> None:
    app, learner_token, admin_token = _tokens(tmp_path)
    payload = {
        "enabled": True,
        "config": {
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4.1-mini",
            "temperature": 0.2,
        },
        "secrets": {"api_key": "sk-admin-secret"},
    }

    with TestClient(app) as client:
        denied = client.get(
            "/admin/integrations",
            headers={"Authorization": f"Bearer {learner_token}"},
        )
        saved = client.put(
            "/admin/integrations/chat",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        listed = client.get(
            "/admin/integrations",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert denied.status_code == 403
    assert saved.status_code == 200
    assert saved.json()["secret_hints"] == {"api_key": "••••cret"}
    assert "sk-admin-secret" not in saved.text
    assert [item["kind"] for item in listed.json()] == [
        "chat",
        "embedding",
        "ocr",
        "object_storage",
    ]


def test_admin_overview_reports_database_and_user_counts(tmp_path) -> None:
    app, _, admin_token = _tokens(tmp_path)

    with TestClient(app) as client:
        response = client.get(
            "/admin/overview",
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "database": "sqlite",
        "pgvector": False,
        "users": 2,
        "integrations_configured": 0,
    }


def test_legacy_model_update_endpoint_is_admin_only(tmp_path) -> None:
    app, learner_token, admin_token = _tokens(tmp_path)
    payload = {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "api_key": "sk-admin-secret",
        "temperature": 0.2,
    }

    with TestClient(app) as client:
        denied = client.put(
            "/settings/model",
            json=payload,
            headers={"Authorization": f"Bearer {learner_token}"},
        )
        saved = client.put(
            "/settings/model",
            json=payload,
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert denied.status_code == 403
    assert saved.status_code == 200
    assert saved.json()["configured"] is True


def test_admin_cannot_bypass_the_server_model_host_allowlist(tmp_path) -> None:
    app, _, admin_token = _tokens(tmp_path)

    with TestClient(app) as client:
        response = client.put(
            "/admin/integrations/embedding",
            json={
                "enabled": True,
                "config": {
                    "base_url": "https://unapproved.example/v1",
                    "model": "embedding-model",
                    "dimensions": 1536,
                },
                "secrets": {"api_key": "sk-admin-secret"},
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert response.status_code == 422
    assert "allowlist" in response.json()["error"]["message"]


def test_admin_cannot_bypass_the_object_storage_host_allowlist(tmp_path) -> None:
    app, _, admin_token = _tokens(tmp_path)

    with TestClient(app) as client:
        response = client.put(
            "/admin/integrations/object_storage",
            json={
                "enabled": True,
                "config": {
                    "endpoint_url": "https://storage.example.com",
                    "bucket": "refineq-private",
                    "region": "auto",
                    "addressing_style": "path",
                    "allow_private_network": False,
                },
                "secrets": {
                    "access_key_id": "access",
                    "secret_access_key": "secret",
                },
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )

    assert response.status_code == 422
    assert "allowlist" in response.json()["error"]["message"]
