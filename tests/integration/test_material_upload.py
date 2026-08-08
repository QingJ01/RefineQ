"""Integration contract for uploading and searching study material."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from pathlib import Path
from threading import Event, get_ident

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from refineq.api.app import create_app
from refineq.config import Settings
from refineq.database.schema import material_chunks, materials
from refineq.knowledge.extract import MaterialExtractionLimitError
from refineq.operations.recovery import RecoveryLease


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
        assert (
            client.get(
                f"/workspaces/{workspace_id}/materials",
                headers=headers,
            ).json()
            == []
        )
        missing = client.get(
            f"/workspaces/{workspace_id}/materials/{material['id']}/download",
            headers=headers,
        )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "material_not_found"


def test_workspace_material_metadata_filters_sort_and_bulk_delete_are_owner_scoped(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        alice = _register(client, "material-organize-alice@example.com")
        bob = _register(client, "material-organize-bob@example.com")
        headers = _headers(alice)
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Organize calculus source material"},
        ).json()["workspace"]["id"]
        uploaded = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files=[
                ("files", ("zeta.txt", b"Limits notes", "text/plain")),
                ("files", ("alpha.txt", b"Derivative notes", "text/plain")),
            ],
        ).json()
        by_filename = {item["filename"]: item for item in uploaded}
        zeta = by_filename["zeta.txt"]
        alpha = by_filename["alpha.txt"]
        zeta_key = app.state.knowledge.get_material_storage_key(
            owner_id=client.get("/auth/me", headers=headers).json()["id"],
            project_id=workspace_id,
            material_id=zeta["id"],
        )

        updated = client.patch(
            f"/workspaces/{workspace_id}/materials/{zeta['id']}",
            headers=headers,
            json={
                "title": "  Calculus handbook  ",
                "tags": [" Exam ", "calculus", "exam"],
            },
        )
        client.patch(
            f"/workspaces/{workspace_id}/materials/{alpha['id']}",
            headers=headers,
            json={"title": "Derivative primer", "tags": ["calculus"]},
        )
        filtered = client.get(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            params={"status": "indexed", "tag": "CALCULUS", "sort": "title"},
        )
        forbidden = client.patch(
            f"/workspaces/{workspace_id}/materials/{zeta['id']}",
            headers=_headers(bob),
            json={"title": "Stolen"},
        )
        deleted = client.request(
            "DELETE",
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            json={"material_ids": [zeta["id"]]},
        )

    assert updated.status_code == 200
    assert updated.json()["title"] == "Calculus handbook"
    assert updated.json()["tags"] == ["Exam", "calculus"]
    assert [item["title"] for item in filtered.json()] == [
        "Calculus handbook",
        "Derivative primer",
    ]
    assert forbidden.status_code == 404
    assert forbidden.json()["error"]["code"] == "workspace_not_found"
    assert deleted.status_code == 204
    with pytest.raises(FileNotFoundError):
        app.state.object_storage.get(zeta_key)
    with app.state.database.session() as session:
        assert session.scalar(
            select(func.count()).select_from(materials).where(
                materials.c.project_id == workspace_id,
                materials.c.material_id == zeta["id"],
            )
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(material_chunks).where(
                material_chunks.c.project_id == workspace_id,
                material_chunks.c.material_id == zeta["id"],
            )
        ) == 0


def test_bulk_material_delete_restores_objects_when_index_cleanup_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app, raise_server_exceptions=False) as client:
        token = _register(client, "bulk-delete-rollback@example.com")
        headers = _headers(token)
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study calculus"},
        ).json()["workspace"]["id"]
        uploaded = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files=[
                ("files", ("notes-a.txt", b"Durable notes A", "text/plain")),
                ("files", ("notes-b.txt", b"Durable notes B", "text/plain")),
            ],
        ).json()
        owner_id = client.get("/auth/me", headers=headers).json()["id"]
        storage_keys = {
            material["id"]: app.state.knowledge.get_material_storage_key(
                owner_id=owner_id,
                project_id=workspace_id,
                material_id=material["id"],
            )
            for material in uploaded
        }

        def fail_delete(**kwargs):
            del kwargs
            raise RuntimeError("index unavailable")

        monkeypatch.setattr(app.state.knowledge, "delete_materials", fail_delete, raising=False)
        failed = client.request(
            "DELETE",
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            json={"material_ids": [material["id"] for material in uploaded]},
        )

    assert failed.status_code == 503
    for material, expected in zip(
        uploaded,
        (b"Durable notes A", b"Durable notes B"),
        strict=True,
    ):
        assert app.state.object_storage.get(storage_keys[material["id"]]) == expected
        assert app.state.knowledge.get_material(
            owner_id=owner_id,
            project_id=workspace_id,
            material_id=material["id"],
        ).id == material["id"]


def test_upload_refuses_to_race_an_active_material_object_deletion(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token = _register(client, "upload-delete-race@example.com")
        project_id = _project(client, token)
        lease = RecoveryLease.acquire(app.state.material_deletions.lease_path)
        assert lease is not None
        try:
            response = client.post(
                f"/projects/{project_id}/materials",
                headers=_headers(token),
                files={"files": ("notes.txt", b"blocked upload", "text/plain")},
            )
        finally:
            lease.release()

        listed = client.get(
            f"/projects/{project_id}/materials",
            headers=_headers(token),
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "material_mutation_busy"
    assert listed.json() == []


def test_upload_revalidates_workspace_after_parsing_before_writing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    materials_router = import_module("refineq.api.routers.materials")
    original_store = materials_router._store_and_index
    store_ready = Event()
    continue_store = Event()

    def delayed_store(*args, **kwargs):
        store_ready.set()
        assert continue_store.wait(timeout=5)
        return original_store(*args, **kwargs)

    monkeypatch.setattr(materials_router, "_store_and_index", delayed_store)

    with TestClient(app) as client:
        token = _register(client, "upload-deleted-workspace-race@example.com")
        headers = _headers(token)
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study upload deletion races"},
        ).json()["workspace"]["id"]

        def upload():
            return client.post(
                f"/workspaces/{workspace_id}/materials",
                headers=headers,
                files={"files": ("orphan.txt", b"must not be orphaned", "text/plain")},
            )

        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(upload)
            assert store_ready.wait(timeout=5)
            deleted = client.delete(f"/workspaces/{workspace_id}", headers=headers)
            continue_store.set()
            uploaded = pending.result(timeout=5)

    assert deleted.status_code == 204
    assert uploaded.status_code == 404
    assert uploaded.json()["error"]["code"] == "workspace_not_found"
    with app.state.database.session() as session:
        assert session.scalar(
            select(func.count()).select_from(materials).where(
                materials.c.project_id == workspace_id
            )
        ) == 0


def test_empty_workspace_delete_serializes_with_an_upload_that_already_holds_the_lease(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    upload_writing = Event()
    delete_waiting = Event()
    continue_upload = Event()
    stored_keys: list[str] = []
    original_put = app.state.object_storage.put
    original_prepare = app.state.material_deletions.prepare

    def delayed_put(*args, **kwargs):
        upload_writing.set()
        assert continue_upload.wait(timeout=5)
        stored = original_put(*args, **kwargs)
        stored_keys.append(stored.key)
        return stored

    def observed_prepare(*args, **kwargs):
        delete_waiting.set()
        return original_prepare(*args, **kwargs)

    monkeypatch.setattr(app.state.object_storage, "put", delayed_put)
    monkeypatch.setattr(app.state.material_deletions, "prepare", observed_prepare)

    with TestClient(app) as client:
        token = _register(client, "empty-workspace-upload-race@example.com")
        headers = _headers(token)
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study empty workspace upload races"},
        ).json()["workspace"]["id"]

        with ThreadPoolExecutor(max_workers=2) as executor:
            upload = executor.submit(
                client.post,
                f"/workspaces/{workspace_id}/materials",
                headers=headers,
                files={"files": ("race.txt", b"serialized upload", "text/plain")},
            )
            assert upload_writing.wait(timeout=5)
            deletion = executor.submit(
                client.delete,
                f"/workspaces/{workspace_id}",
                headers=headers,
            )
            assert delete_waiting.wait(timeout=5)
            continue_upload.set()
            uploaded = upload.result(timeout=5)
            deleted = deletion.result(timeout=5)
        missing_workspace = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=headers,
        )

    assert uploaded.status_code == 201
    assert deleted.status_code == 204
    assert missing_workspace.status_code == 404
    with app.state.database.session() as session:
        assert session.scalar(
            select(func.count()).select_from(materials).where(
                materials.c.project_id == workspace_id
            )
        ) == 0
    assert stored_keys
    for storage_key in stored_keys:
        with pytest.raises(FileNotFoundError):
            app.state.object_storage.get(storage_key)


def test_workspace_delete_restores_material_objects_when_index_cleanup_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app, raise_server_exceptions=False) as client:
        token = _register(client, "workspace-delete-compensation@example.com")
        headers = _headers(token)
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study durable workspace deletion"},
        ).json()["workspace"]["id"]
        material = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files={"files": ("notes.txt", b"workspace material", "text/plain")},
        ).json()[0]

        def fail_delete(**kwargs):
            del kwargs
            raise RuntimeError("index unavailable")

        monkeypatch.setattr(app.state.knowledge, "delete_materials", fail_delete)
        failed = client.delete(f"/workspaces/{workspace_id}", headers=headers)
        restored = client.get(
            f"/workspaces/{workspace_id}/materials/{material['id']}/download",
            headers=headers,
        )

    assert failed.status_code == 500
    assert restored.status_code == 200
    assert restored.content == b"workspace material"


def test_workspace_delete_restores_state_when_learning_cleanup_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app, raise_server_exceptions=False) as client:
        token = _register(client, "workspace-delete-learning-rollback@example.com")
        headers = _headers(token)
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study complete workspace rollback"},
        ).json()["workspace"]["id"]
        material = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files={"files": ("notes.txt", b"workspace rollback material", "text/plain")},
        ).json()[0]
        original_delete = app.state.learning.delete

        def delete_then_fail(owner_id: str, project_id: str) -> None:
            original_delete(owner_id, project_id)
            raise RuntimeError("learning cleanup failed")

        monkeypatch.setattr(app.state.learning, "delete", delete_then_fail)
        failed = client.delete(f"/workspaces/{workspace_id}", headers=headers)
        snapshot = client.get(f"/workspaces/{workspace_id}/snapshot", headers=headers)
        restored = client.get(
            f"/workspaces/{workspace_id}/materials/{material['id']}/download",
            headers=headers,
        )

    assert failed.status_code == 500
    assert snapshot.status_code == 200
    assert restored.status_code == 200
    assert restored.content == b"workspace rollback material"


def test_workspace_delete_stays_committed_when_recovery_journal_cleanup_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    deletion_module = import_module("refineq.knowledge.deletion")
    original_remove_tree = deletion_module.durable_remove_tree

    with TestClient(app) as client:
        token = _register(client, "workspace-delete-journal-cleanup@example.com")
        headers = _headers(token)
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study committed deletion cleanup"},
        ).json()["workspace"]["id"]
        material = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files={"files": ("notes.txt", b"delete completely", "text/plain")},
        ).json()[0]

        def remove_then_fail(path: Path) -> None:
            original_remove_tree(path)
            raise OSError("directory fsync failed after removal")

        monkeypatch.setattr(deletion_module, "durable_remove_tree", remove_then_fail)
        deleted = client.delete(f"/workspaces/{workspace_id}", headers=headers)
        missing_workspace = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=headers,
        )

    assert deleted.status_code == 204
    assert missing_workspace.status_code == 404
    with app.state.database.session() as session:
        assert session.scalar(
            select(func.count()).select_from(materials).where(
                materials.c.material_id == material["id"]
            )
        ) == 0
    assert not any(path.name == material["id"] for path in app.state.settings.data_root.rglob("*"))


def test_pending_bulk_material_delete_is_recovered_after_process_interruption(
    tmp_path: Path,
) -> None:
    settings = Settings(data_root=tmp_path / "data", _env_file=None)
    app = create_app(settings)

    with TestClient(app) as client:
        token = _register(client, "bulk-delete-recovery@example.com")
        headers = _headers(token)
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study recovery journals"},
        ).json()["workspace"]["id"]
        material = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files={"files": ("notes.txt", b"Recover this material", "text/plain")},
        ).json()[0]
        owner_id = client.get("/auth/me", headers=headers).json()["id"]
        storage_key = app.state.knowledge.get_material_storage_key(
            owner_id=owner_id,
            project_id=workspace_id,
            material_id=material["id"],
        )
        app.state.material_deletions.prepare(
            owner_id=owner_id,
            project_id=workspace_id,
            material_ids=[material["id"]],
        )
        app.state.object_storage.delete(storage_key)

    recovered_app = create_app(settings)
    try:
        assert recovered_app.state.object_storage.get(storage_key) == b"Recover this material"
        assert recovered_app.state.knowledge.get_material(
            owner_id=owner_id,
            project_id=workspace_id,
            material_id=material["id"],
        ).id == material["id"]
        recovery_root = settings.data_root / "recovery" / "material-deletions"
        assert not any(path.is_dir() for path in recovery_root.iterdir())
    finally:
        recovered_app.state.account_deletions.close()
        recovered_app.state.material_deletions.close()
        recovered_app.state.database.close()


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


def test_failed_material_index_delete_restores_the_original_object(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app, raise_server_exceptions=False) as client:
        token = _register(client, "delete-compensation@example.com")
        project_id = _project(client, token)
        uploaded = client.post(
            f"/projects/{project_id}/materials",
            headers=_headers(token),
            files={"files": ("notes.txt", b"Durable notes", "text/plain")},
        ).json()[0]

        def fail_delete(**kwargs):
            del kwargs
            raise RuntimeError("index unavailable")

        monkeypatch.setattr(app.state.knowledge, "delete_materials", fail_delete)
        failed = client.delete(
            f"/projects/{project_id}/materials/{uploaded['id']}",
            headers=_headers(token),
        )
        restored = client.get(
            f"/projects/{project_id}/materials/{uploaded['id']}/download",
            headers=_headers(token),
        )

    assert failed.status_code == 503
    assert restored.status_code == 200
    assert restored.content == b"Durable notes"


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
    assert (
        app.state.knowledge.list_materials(
            owner_id=owner.id,
            project_id=workspace_id,
        )
        == []
    )
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
