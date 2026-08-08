"""Integration tests for the minimal RefineQ API."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.config import Settings
from refineq.storage.sql_store import SqlRecordStore


def _client(data_root: Path) -> TestClient:
    settings = Settings(data_root=data_root, _env_file=None)
    return TestClient(create_app(settings))


def test_liveness_does_not_depend_on_storage(tmp_path: Path) -> None:
    with _client(tmp_path / "data") as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_proves_the_data_root_is_writable(tmp_path: Path) -> None:
    data_root = tmp_path / "data"

    with _client(data_root) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"storage": "ok", "database": "ok"},
    }
    assert data_root.is_dir()
    assert (data_root / "system" / "refineq.sqlite3").is_file()


def test_http_errors_use_the_refineq_error_envelope(tmp_path: Path) -> None:
    with _client(tmp_path / "data") as client:
        response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Not Found",
        }
    }
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_application_uses_the_sql_record_store(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    assert isinstance(app.state.store, SqlRecordStore)
    assert app.state.database.ping() is True


def test_readiness_rejects_an_unavailable_database(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    app.state.database.ping = lambda: False

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Database is not ready"
