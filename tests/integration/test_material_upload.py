"""Integration contract for uploading and searching study material."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import get_ident

import httpx
import pytest
from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.config import Settings
from refineq.knowledge.extract import MaterialExtractionLimitError


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


def test_pdf_extraction_limit_does_not_fall_back_to_ocr(tmp_path: Path, monkeypatch) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    ocr_calls: list[str] = []

    def extraction_limit(*args, **kwargs):
        raise MaterialExtractionLimitError("PDF exceeds the configured page limit")

    class AvailableOcr:
        @staticmethod
        def available() -> bool:
            return True

        @staticmethod
        def extract(filename: str, *args, **kwargs) -> str:
            ocr_calls.append(filename)
            return "OCR text"

    monkeypatch.setattr(
        "refineq.api.routers.materials.extract_text_isolated",
        extraction_limit,
    )
    app.state.ocr = AvailableOcr()

    with TestClient(app) as client:
        token = _register(client, "extraction-limit@example.com")
        project_id = _project(client, token)
        response = client.post(
            f"/projects/{project_id}/materials",
            headers=_headers(token),
            files={"files": ("large.pdf", b"%PDF-1.7", "application/pdf")},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "material_extraction_limit"
    assert ocr_calls == []


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


def test_workspace_materials_can_be_listed_downloaded_and_deleted(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token = _register(client, "workspace-materials@example.com")
        headers = _headers(token)
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "学习微积分"},
        ).json()["workspace"]["id"]
        upload = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files={
                "files": (
                    "limits.txt",
                    b"Limits describe an approached value.",
                    "text/plain",
                )
            },
        )
        material = upload.json()[0]

        listed = client.get(f"/workspaces/{workspace_id}/materials", headers=headers)
        downloaded = client.get(
            f"/workspaces/{workspace_id}/materials/{material['id']}/download",
            headers=headers,
        )

        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [material["id"]]
        assert downloaded.status_code == 200
        assert downloaded.content == b"Limits describe an approached value."
        assert 'filename="limits.txt"' in downloaded.headers["content-disposition"]

        deleted = client.delete(
            f"/workspaces/{workspace_id}/materials/{material['id']}",
            headers=headers,
        )
        assert deleted.status_code == 204
        assert client.get(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
        ).json() == []
        missing = client.get(
            f"/workspaces/{workspace_id}/materials/{material['id']}/download",
            headers=headers,
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "material_not_found"


def test_workspace_material_delete_is_owner_scoped(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        alice = _register(client, "material-alice@example.com")
        bob = _register(client, "material-bob@example.com")
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=_headers(alice),
            json={"intent": "学习微积分"},
        ).json()["workspace"]["id"]
        material_id = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=_headers(alice),
            files={"files": ("notes.txt", b"Calculus notes", "text/plain")},
        ).json()[0]["id"]

        forbidden = client.delete(
            f"/workspaces/{workspace_id}/materials/{material_id}",
            headers=_headers(bob),
        )

    assert forbidden.status_code == 404
    assert forbidden.json()["error"]["code"] == "workspace_not_found"


def test_deleting_workspace_removes_indexed_and_original_materials(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token = _register(client, "workspace-cleanup@example.com")
        owner = app.state.identity.authenticate(
            email="workspace-cleanup@example.com",
            password="correct-horse-battery-staple",
        )
        headers = _headers(token)
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "学习微积分"},
        ).json()["workspace"]["id"]
        material = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files={"files": ("notes.txt", b"Calculus notes", "text/plain")},
        ).json()[0]
        storage_key = app.state.knowledge.get_material_storage_key(
            owner_id=owner.id,
            project_id=workspace_id,
            material_id=material["id"],
        )
        stored_path = tmp_path / "data" / storage_key
        assert stored_path.exists()

        deleted = client.delete(f"/workspaces/{workspace_id}", headers=headers)

    assert deleted.status_code == 204
    assert app.state.knowledge.list_materials(
        owner_id=owner.id,
        project_id=workspace_id,
    ) == []
    assert not stored_path.exists()


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


@pytest.mark.asyncio
async def test_storage_and_indexing_run_outside_the_event_loop_thread(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    event_loop_thread = get_ident()
    storage_threads: list[int] = []
    original_put = app.state.object_storage.put

    def recording_put(**kwargs):
        storage_threads.append(get_ident())
        return original_put(**kwargs)

    monkeypatch.setattr(app.state.object_storage, "put", recording_put)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        registered = await client.post(
            "/auth/register",
            json={
                "email": "worker-upload@example.com",
                "password": "correct-horse-battery-staple",
                "display_name": "Learner",
            },
        )
        token = registered.json()["access_token"]
        project = await client.post(
            "/projects",
            headers=_headers(token),
            json={"name": "Calculus"},
        )
        response = await client.post(
            f"/projects/{project.json()['id']}/materials",
            headers=_headers(token),
            files={"files": ("notes.txt", b"Limits notes", "text/plain")},
        )

    assert response.status_code == 201
    assert storage_threads
    assert all(thread_id != event_loop_thread for thread_id in storage_threads)
