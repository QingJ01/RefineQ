"""Integration tests for the minimal RefineQ API."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.config import Settings


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
        "checks": {"storage": "ok"},
    }
    assert data_root.is_dir()
    assert list(data_root.iterdir()) == []


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
