"""Integration contract for uploading and searching study material."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
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


def test_mixed_valid_and_invalid_batch_is_all_or_nothing(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token = _register(client, "atomic-upload@example.com")
        project_id = _project(client, token)
        response = client.post(
            f"/projects/{project_id}/materials",
            headers=_headers(token),
            files=[
                ("files", ("valid.txt", b"Useful calculus notes.", "text/plain")),
                ("files", ("broken.pdf", b"not a pdf", "application/pdf")),
            ],
        )

    assert response.status_code == 422
    assert (
        app.state.knowledge.list_materials(
            owner_id=app.state.identity.authenticate(
                email="atomic-upload@example.com",
                password="correct-horse-battery-staple",
            ).id,
            project_id=project_id,
        )
        == []
    )
    material_dir = (
        tmp_path
        / "data"
        / "users"
        / app.state.identity.authenticate(
            email="atomic-upload@example.com",
            password="correct-horse-battery-staple",
        ).id
        / "knowledge"
        / "projects"
        / project_id
        / "materials"
    )
    assert not material_dir.exists() or list(material_dir.iterdir()) == []


def test_per_user_material_quota_is_enforced_before_second_upload(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            data_root=tmp_path / "data",
            material_max_count_per_user=1,
            material_max_bytes_per_user=1_000,
            _env_file=None,
        )
    )

    with TestClient(app) as client:
        token = _register(client, "quota-upload@example.com")
        project_id = _project(client, token)
        first = client.post(
            f"/projects/{project_id}/materials",
            headers=_headers(token),
            files={"files": ("one.txt", b"First notes", "text/plain")},
        )
        second = client.post(
            f"/projects/{project_id}/materials",
            headers=_headers(token),
            files={"files": ("two.txt", b"Second notes", "text/plain")},
        )

    assert first.status_code == 201
    assert second.status_code == 413
    assert second.json()["error"]["code"] == "material_quota"


def test_concurrent_uploads_cannot_cross_owner_material_quota(tmp_path: Path, monkeypatch) -> None:
    app = create_app(
        Settings(
            data_root=tmp_path / "data",
            material_max_count_per_user=1,
            material_max_bytes_per_user=1_000,
            material_upload_max_concurrent_global=2,
            material_upload_max_concurrent_per_user=2,
            mutation_rate_limit_requests=100,
            _env_file=None,
        )
    )
    original_add = app.state.knowledge.add_documents

    def slow_add(*args, **kwargs):
        time.sleep(0.05)
        return original_add(*args, **kwargs)

    monkeypatch.setattr(app.state.knowledge, "add_documents", slow_add)

    with TestClient(app) as client:
        token = _register(client, "concurrent-upload@example.com")
        project_id = _project(client, token)

        def upload(index: int) -> int:
            response = client.post(
                f"/projects/{project_id}/materials",
                headers=_headers(token),
                files={"files": (f"notes-{index}.txt", f"Notes {index}".encode(), "text/plain")},
            )
            return response.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = sorted(executor.map(upload, range(2)))

    assert statuses == [201, 413]
