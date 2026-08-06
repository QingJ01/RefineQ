"""Integration contract for uploading and searching study material."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.config import Settings


def _register(client: TestClient, email: str) -> str:
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "correct-horse-battery-staple",
            "display_name": "Learner",
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _project(client: TestClient, token: str) -> str:
    response = client.post(
        "/projects",
        headers=_headers(token),
        json={"name": "Calculus"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_upload_status_and_search_are_project_scoped(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        alice_token = _register(client, "alice@example.com")
        bob_token = _register(client, "bob@example.com")
        project_id = _project(client, alice_token)
        upload = client.post(
            f"/projects/{project_id}/materials",
            headers=_headers(alice_token),
            files={
                "files": (
                    "calculus.txt",
                    b"The derivative is the local rate of change.",
                    "text/plain",
                )
            },
        )
        assert upload.status_code == 201
        material = upload.json()[0]
        assert material["status"] == "indexed"

        status_response = client.get(
            f"/projects/{project_id}/materials/{material['id']}",
            headers=_headers(alice_token),
        )
        search = client.get(
            f"/projects/{project_id}/materials/search",
            headers=_headers(alice_token),
            params={"q": "derivative"},
        )
        forbidden = client.get(
            f"/projects/{project_id}/materials/search",
            headers=_headers(bob_token),
            params={"q": "derivative"},
        )

    assert status_response.status_code == 200
    assert status_response.json()["filename"] == "calculus.txt"
    assert search.status_code == 200
    assert search.json()[0]["citation_id"].startswith(material["id"])
    assert forbidden.status_code == 404
    assert forbidden.json()["error"]["code"] == "project_not_found"


def test_mime_mismatch_has_a_stable_error(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token = _register(client, "learner@example.com")
        project_id = _project(client, token)
        response = client.post(
            f"/projects/{project_id}/materials",
            headers=_headers(token),
            files={"files": ("fake.pdf", b"not a pdf", "text/plain")},
        )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_material"
