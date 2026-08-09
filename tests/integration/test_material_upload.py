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
from refineq.database.schema import material_chunks, materials, workspace_materials
from refineq.knowledge.extract import MaterialExtractionLimitError
from refineq.knowledge.index import MaterialNotFoundError
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


def test_global_library_uploads_before_a_workspace_and_attaches_later(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token = _register(client, "library@example.com")
        headers = _headers(token)
        uploaded = client.post(
            "/materials/library",
            headers=headers,
            files={"files": ("biology.txt", b"Cells contain hereditary DNA.", "text/plain")},
        )
        assert uploaded.status_code == 201
        library_material = uploaded.json()[0]
        assert library_material["project_id"] == "library"

        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Prepare for a biology exam"},
        ).json()["workspace"]["id"]
        attached = client.post(
            f"/materials/library/library/{library_material['id']}/attach/{workspace_id}",
            headers=headers,
        )
        assert attached.status_code == 201
        assert attached.json()["project_id"] == "library"

        collection = client.get("/materials/library", headers=headers)
        assert collection.status_code == 200
        assert {item["project_id"] for item in collection.json()} == {"library"}
        assert len(collection.json()) == 1
        assert collection.json()[0]["workspace_ids"] == [workspace_id]

        searchable = client.get(
            f"/workspaces/{workspace_id}/materials/search",
            headers=headers,
            params={"q": "hereditary DNA"},
        )
        assert searchable.status_code == 200
        assert searchable.json()[0]["filename"] == "biology.txt"


def test_global_library_delete_removes_links_and_does_not_reattach_same_content(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    payload = b"Cells contain hereditary DNA."
    with TestClient(app) as client:
        token = _register(client, "library-delete@example.com")
        headers = _headers(token)
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Prepare for a biology exam"},
        ).json()["workspace"]["id"]
        material = client.post(
            "/materials/library",
            headers=headers,
            files={"files": ("biology.txt", payload, "text/plain")},
        ).json()[0]
        client.post(
            f"/materials/library/library/{material['id']}/attach/{workspace_id}",
            headers=headers,
        )
        analyzed = client.post(
            f"/workspaces/{workspace_id}/materials/{material['id']}/analysis",
            headers=headers,
        )

        deleted = client.delete(
            f"/materials/library/{material['id']}",
            headers=headers,
        )
        reuploaded = client.post(
            "/materials/library",
            headers=headers,
            files={"files": ("biology-v2.txt", payload, "text/plain")},
        )
        workspace_materials_after = client.get(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
        )
        client.post(
            f"/materials/library/library/{material['id']}/attach/{workspace_id}",
            headers=headers,
        )
        stale_analysis = client.get(
            f"/workspaces/{workspace_id}/materials/{material['id']}/analysis",
            headers=headers,
        )

    assert analyzed.status_code == 200
    assert deleted.status_code == 204
    assert reuploaded.status_code == 201
    assert reuploaded.json()[0]["id"] == material["id"]
    assert stale_analysis.status_code == 404
    assert workspace_materials_after.json() == []
    with app.state.database.session() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(workspace_materials)
                .where(workspace_materials.c.material_id == material["id"])
            )
            == 1
        )


def test_analysis_finishing_after_physical_delete_cannot_recreate_orphan_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    analysis_started = Event()
    continue_analysis = Event()
    original_analyze = app.state.material_analysis.analyze

    def blocking_analyze(**kwargs):
        analysis_started.set()
        assert continue_analysis.wait(timeout=3)
        return original_analyze(**kwargs)

    monkeypatch.setattr(app.state.material_analysis, "analyze", blocking_analyze)

    with TestClient(app) as client:
        token = _register(client, "analysis-delete-race@example.com")
        headers = _headers(token)
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study material analysis deletion races"},
        ).json()["workspace"]["id"]
        material = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files={
                "files": (
                    "limits.txt",
                    b"Limits describe local behavior near a point.",
                    "text/plain",
                )
            },
        ).json()[0]

        with ThreadPoolExecutor(max_workers=2) as executor:
            analysis_future = executor.submit(
                client.post,
                f"/workspaces/{workspace_id}/materials/{material['id']}/analysis",
                headers=headers,
            )
            assert analysis_started.wait(timeout=3)
            delete_future = executor.submit(
                client.delete,
                f"/materials/library/{material['id']}",
                headers=headers,
            )
            try:
                deleted = delete_future.result(timeout=1)
            finally:
                continue_analysis.set()
            analyzed = analysis_future.result(timeout=3)

        stale_analysis = client.get(
            f"/workspaces/{workspace_id}/materials/{material['id']}/analysis",
            headers=headers,
        )

    assert deleted.status_code == 204
    assert analyzed.status_code == 404
    assert analyzed.json()["error"]["code"] == "material_not_found"
    assert stale_analysis.status_code == 404
    with app.state.database.session() as session:
        assert (
            session.execute(
                select(func.count())
                .select_from(materials)
                .where(materials.c.material_id == material["id"])
            ).scalar_one()
            == 0
        )


def test_duplicate_filename_upload_is_rejected_and_existing_material_can_be_attached(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token = _register(client, "deduplicated-library@example.com")
        headers = _headers(token)
        workspace_ids = [
            client.post(
                "/workspaces/resolve",
                headers=headers,
                json={"intent": intent},
            ).json()["workspace"]["id"]
            for intent in ("Study cell biology", "Prepare advanced French grammar")
        ]
        first = client.post(
            f"/workspaces/{workspace_ids[0]}/materials",
            headers=headers,
            files={"files": ("biology.txt", b"Cells contain hereditary DNA.", "text/plain")},
        )
        assert first.status_code == 201
        uploaded = first.json()[0]
        duplicate = client.post(
            f"/workspaces/{workspace_ids[1]}/materials",
            headers=headers,
            files={"files": ("biology.txt", b"Different contents.", "text/plain")},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "material_filename_exists"
        attached = client.post(
            f"/materials/library/library/{uploaded['id']}/attach/{workspace_ids[1]}",
            headers=headers,
        )
        assert attached.status_code == 201
        owner_id = client.get("/auth/me", headers=headers).json()["id"]

    with app.state.database.session() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(materials).where(materials.c.owner_id == owner_id)
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(workspace_materials)
                .where(workspace_materials.c.owner_id == owner_id)
            )
            == 2
        )


def test_duplicate_filename_in_one_upload_is_rejected(tmp_path: Path) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token = _register(client, "duplicate-batch@example.com")
        response = client.post(
            "/materials/library",
            headers=_headers(token),
            files=[
                ("files", ("Notes.txt", b"First notes", "text/plain")),
                ("files", ("notes.txt", b"Second notes", "text/plain")),
            ],
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "material_filename_exists"


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
    assert app.state.object_storage.get(zeta_key) == b"Limits notes"
    with pytest.raises(MaterialNotFoundError):
        app.state.knowledge.get_material(
            owner_id=client.get("/auth/me", headers=headers).json()["id"],
            project_id=workspace_id,
            material_id=zeta["id"],
        )
    with app.state.database.session() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(materials)
                .where(
                    materials.c.project_id == "library",
                    materials.c.material_id == zeta["id"],
                )
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(material_chunks)
                .where(
                    material_chunks.c.project_id == "library",
                    material_chunks.c.material_id == zeta["id"],
                )
            )
            > 0
        )


def test_bulk_workspace_remove_does_not_delete_shared_objects(
    tmp_path: Path,
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

        failed = client.request(
            "DELETE",
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            json={"material_ids": [material["id"] for material in uploaded]},
        )

    assert failed.status_code == 204
    for material, expected in zip(
        uploaded,
        (b"Durable notes A", b"Durable notes B"),
        strict=True,
    ):
        assert app.state.object_storage.get(storage_keys[material["id"]]) == expected
        with pytest.raises(MaterialNotFoundError):
            app.state.knowledge.get_material(
                owner_id=owner_id,
                project_id=workspace_id,
                material_id=material["id"],
            )
        assert (
            app.state.knowledge.get_material(
                owner_id=owner_id,
                project_id="library",
                material_id=material["id"],
            ).id
            == material["id"]
        )


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
        assert (
            session.scalar(
                select(func.count())
                .select_from(materials)
                .where(materials.c.project_id == workspace_id)
            )
            == 0
        )


def test_workspace_deleted_during_upload_does_not_create_an_orphan_link(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    upload_writing = Event()
    continue_upload = Event()
    stored_keys: list[str] = []
    original_put = app.state.object_storage.put

    def delayed_put(*args, **kwargs):
        upload_writing.set()
        assert continue_upload.wait(timeout=5)
        stored = original_put(*args, **kwargs)
        stored_keys.append(stored.key)
        return stored

    monkeypatch.setattr(app.state.object_storage, "put", delayed_put)

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
            deleted = deletion.result(timeout=5)
            continue_upload.set()
            uploaded = upload.result(timeout=5)
        deleted_after_upload = client.delete(
            f"/workspaces/{workspace_id}",
            headers=headers,
        )
        missing_workspace = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=headers,
        )

    assert deleted.status_code == 409
    assert deleted.json()["error"]["code"] == "material_mutation_busy"
    assert uploaded.status_code == 201
    assert deleted_after_upload.status_code == 204
    assert missing_workspace.status_code == 404
    with app.state.database.session() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(materials)
                .where(materials.c.filename == "race.txt")
            )
            == 1
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(workspace_materials)
                .where(workspace_materials.c.workspace_id == workspace_id)
            )
            == 0
        )
    assert stored_keys
    for storage_key in stored_keys:
        assert app.state.object_storage.get(storage_key) == b"serialized upload"


def test_attach_revalidates_workspace_after_a_concurrent_workspace_delete(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))

    with TestClient(app) as client:
        token = _register(client, "attach-deleted-workspace-race@example.com")
        headers = _headers(token)
        owner_id = client.get("/auth/me", headers=headers).json()["id"]
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study attach and workspace deletion races"},
        ).json()["workspace"]["id"]
        material = client.post(
            "/materials/library",
            headers=headers,
            files={"files": ("notes.txt", b"Stable library evidence.", "text/plain")},
        ).json()[0]

        materials_router = import_module("refineq.api.routers.materials")
        original_require_project = materials_router._require_project
        workspace_validated = Event()
        continue_attach = Event()

        def controlled_require_project(request, request_owner_id, project_id):
            result = original_require_project(request, request_owner_id, project_id)
            if not workspace_validated.is_set():
                workspace_validated.set()
                assert continue_attach.wait(timeout=3)
            return result

        monkeypatch.setattr(
            materials_router,
            "_require_project",
            controlled_require_project,
        )

        def attach_material():
            return client.post(
                f"/materials/library/library/{material['id']}/attach/{workspace_id}",
                headers=headers,
            )

        with ThreadPoolExecutor(max_workers=1) as executor:
            attached_future = executor.submit(attach_material)
            assert workspace_validated.wait(timeout=3)
            app.state.workspace_service.delete(owner_id, workspace_id)
            continue_attach.set()
            attached = attached_future.result(timeout=3)

    assert attached.status_code == 404
    assert attached.json()["error"]["code"] == "workspace_not_found"
    with app.state.database.session() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(workspace_materials)
                .where(
                    workspace_materials.c.owner_id == owner_id,
                    workspace_materials.c.workspace_id == workspace_id,
                )
            )
            == 0
        )


def test_workspace_delete_restores_state_when_unlinking_materials_fails(
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

        monkeypatch.setattr(app.state.knowledge, "unlink_materials", fail_delete)
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


def test_workspace_delete_keeps_the_document_in_the_library(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
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

        deleted = client.delete(f"/workspaces/{workspace_id}", headers=headers)
        missing_workspace = client.get(
            f"/workspaces/{workspace_id}/snapshot",
            headers=headers,
        )

    assert deleted.status_code == 204
    assert missing_workspace.status_code == 404
    with app.state.database.session() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(materials)
                .where(materials.c.material_id == material["id"])
            )
            == 1
        )
    assert any(path.name == material["id"] for path in app.state.settings.data_root.rglob("*"))


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
        assert (
            recovered_app.state.knowledge.get_material(
                owner_id=owner_id,
                project_id=workspace_id,
                material_id=material["id"],
            ).id
            == material["id"]
        )
        recovery_root = settings.data_root / "recovery" / "material-deletions"
        assert not any(path.is_dir() for path in recovery_root.iterdir())
    finally:
        recovered_app.state.account_deletions.close()
        recovered_app.state.material_deletions.close()
        recovered_app.state.database.close()


def test_pending_library_delete_restores_analysis_after_crash_before_index_commit(
    tmp_path: Path,
) -> None:
    settings = Settings(data_root=tmp_path / "data", _env_file=None)
    app = create_app(settings)

    with TestClient(app) as client:
        token = _register(client, "analysis-delete-recovery@example.com")
        headers = _headers(token)
        owner_id = client.get("/auth/me", headers=headers).json()["id"]
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study durable analysis deletion"},
        ).json()["workspace"]["id"]
        material = client.post(
            f"/workspaces/{workspace_id}/materials",
            headers=headers,
            files={"files": ("notes.txt", b"Limits describe local behavior.", "text/plain")},
        ).json()[0]
        analyzed = client.post(
            f"/workspaces/{workspace_id}/materials/{material['id']}/analysis",
            headers=headers,
        )
        assert analyzed.status_code == 200

        storage_key = app.state.knowledge.get_material_storage_key(
            owner_id=owner_id,
            project_id="library",
            material_id=material["id"],
        )
        pending = app.state.material_deletions.prepare(
            owner_id=owner_id,
            project_id="library",
            material_ids=[material["id"]],
        )
        # Simulate a process dying after deleting the blob and analysis but
        # before the canonical SQL material transaction commits.
        app.state.object_storage.delete(storage_key)
        app.state.material_analyses.delete(owner_id, "library", material["id"])
        assert pending.directory.exists()

    recovered_app = create_app(settings)
    try:
        with TestClient(recovered_app) as recovered_client:
            restored = recovered_client.get(
                f"/workspaces/{workspace_id}/materials/{material['id']}/analysis",
                headers=headers,
            )
        assert restored.status_code == 200
        assert restored.json()["material_id"] == material["id"]
        assert recovered_app.state.object_storage.get(storage_key) == (
            b"Limits describe local behavior."
        )
    finally:
        recovered_app.state.account_deletions.close()
        recovered_app.state.material_deletions.close()
        recovered_app.state.database.close()


def test_physical_bulk_delete_uses_one_atomic_index_transaction(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    with TestClient(app) as client:
        token = _register(client, "atomic-library-delete@example.com")
        headers = _headers(token)
        uploaded = client.post(
            "/materials/library",
            headers=headers,
            files=[
                ("files", ("one.txt", b"First durable note", "text/plain")),
                ("files", ("two.txt", b"Second durable note", "text/plain")),
            ],
        ).json()
        owner_id = client.get("/auth/me", headers=headers).json()["id"]
        ids = [item["id"] for item in uploaded]
        calls: list[list[str]] = []
        original_delete = app.state.knowledge.delete_materials

        def capture_batch(**kwargs):
            calls.append(list(kwargs["material_ids"]))
            return original_delete(**kwargs)

        monkeypatch.setattr(app.state.knowledge, "delete_materials", capture_batch)
        pending = app.state.material_deletions.prepare(
            owner_id=owner_id,
            project_id="library",
            material_ids=ids,
        )
        app.state.material_deletions.complete(pending)

    assert calls == [ids]


def test_migrated_legacy_storage_key_rollback_restores_the_original_object(
    tmp_path: Path,
) -> None:
    app = create_app(Settings(data_root=tmp_path / "data", _env_file=None))
    with TestClient(app) as client:
        token = _register(client, "migrated-object-rollback@example.com")
        headers = _headers(token)
        owner_id = client.get("/auth/me", headers=headers).json()["id"]
        workspace_id = client.post(
            "/workspaces/resolve",
            headers=headers,
            json={"intent": "Study migrated material"},
        ).json()["workspace"]["id"]
        material_id = "material-migrated"
        legacy = app.state.object_storage.put(
            owner_id=owner_id,
            workspace_id=workspace_id,
            material_id=material_id,
            filename="legacy.txt",
            payload=b"legacy object bytes",
        )
        app.state.knowledge.add_document(
            owner_id=owner_id,
            project_id="library",
            material_id=material_id,
            filename="legacy.txt",
            text="legacy object bytes",
            storage_key=legacy.key,
        )
        pending = app.state.material_deletions.prepare(
            owner_id=owner_id,
            project_id="library",
            material_ids=[material_id],
        )
        app.state.object_storage.delete(legacy.key)

        app.state.material_deletions.rollback(pending)

        assert app.state.object_storage.get(legacy.key) == b"legacy object bytes"
        with pytest.raises(FileNotFoundError):
            app.state.object_storage.get(f"users/{owner_id}/documents/{material_id}")


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


def test_legacy_project_remove_unlinks_without_deleting_the_document(
    tmp_path: Path,
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

        failed = client.delete(
            f"/projects/{project_id}/materials/{uploaded['id']}",
            headers=_headers(token),
        )
        restored = client.get(
            f"/projects/{project_id}/materials/{uploaded['id']}/download",
            headers=_headers(token),
        )

    assert failed.status_code == 204
    assert restored.status_code == 404


def test_deleting_workspace_removes_only_links_and_keeps_original_materials(tmp_path: Path) -> None:
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
    assert stored_path.exists()
    assert (
        app.state.knowledge.get_material(
            owner_id=owner.id,
            project_id="library",
            material_id=material["id"],
        ).id
        == material["id"]
    )


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
