"""Authenticated material upload, status, and search endpoints."""

from __future__ import annotations

import os
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status

from refineq.api.dependencies import CurrentUser
from refineq.knowledge.extract import MaterialExtractionError, extract_text
from refineq.knowledge.index import MaterialNotFoundError, MaterialRecord, SearchResult
from refineq.knowledge.policy import MaterialPolicy, MaterialPolicyError, UploadDescriptor
from refineq.storage.json_store import RecordNotFoundError

router = APIRouter(prefix="/projects/{project_id}/materials", tags=["materials"])
workspace_router = APIRouter(
    prefix="/workspaces/{workspace_id}/materials",
    tags=["materials"],
)
_policy = MaterialPolicy()


def _require_project(request: Request, owner_id: str, project_id: str) -> None:
    try:
        request.app.state.projects.get(owner_id, project_id)
    except RecordNotFoundError as error:
        try:
            request.app.state.workspaces.get(owner_id, project_id)
        except RecordNotFoundError:
            workspace_route = request.url.path.startswith("/workspaces/")
            code = "workspace_not_found" if workspace_route else "project_not_found"
            message = "Learning space not found" if workspace_route else "Project not found"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": code, "message": message},
            ) from error


def _material_error(error: MaterialPolicyError) -> HTTPException:
    status_code = (
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
        if error.code == "material_limit"
        else status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    )
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": str(error)},
    )


def _write_material(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.stem}-",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as temporary_file:
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


@router.post("", response_model=list[MaterialRecord], status_code=status.HTTP_201_CREATED)
async def upload_materials(
    project_id: str,
    request: Request,
    user: CurrentUser,
    files: Annotated[list[UploadFile], File()],
) -> list[MaterialRecord]:
    _require_project(request, user.id, project_id)
    if len(files) > _policy.max_files:
        raise _material_error(
            MaterialPolicyError("Too many files in one upload", code="material_limit")
        )

    loaded: list[tuple[UploadFile, bytes]] = []
    for upload in files:
        payload = await upload.read(_policy.max_file_bytes + 1)
        loaded.append((upload, payload))
    descriptors = [
        UploadDescriptor(
            filename=upload.filename or "",
            content_type=upload.content_type or "application/octet-stream",
            size=len(payload),
        )
        for upload, payload in loaded
    ]
    try:
        _policy.validate_batch(descriptors)
    except MaterialPolicyError as error:
        raise _material_error(error) from error

    records = []
    for (upload, payload), descriptor in zip(loaded, descriptors, strict=True):
        try:
            text = extract_text(descriptor.filename, descriptor.content_type, payload)
        except MaterialExtractionError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "material_extraction_failed",
                    "message": str(error),
                },
            ) from error
        material_id = f"material_{sha256(project_id.encode() + payload).hexdigest()[:20]}"
        extension = Path(descriptor.filename).suffix.lower()
        material_path = (
            request.app.state.settings.data_root
            / "users"
            / user.id
            / "knowledge"
            / "projects"
            / project_id
            / "materials"
            / f"{material_id}{extension}"
        )
        _write_material(material_path, payload)
        records.append(
            request.app.state.knowledge.add_document(
                owner_id=user.id,
                project_id=project_id,
                material_id=material_id,
                filename=descriptor.filename,
                content_type=descriptor.content_type,
                size=len(payload),
                text=text,
            )
        )
        await upload.close()
    return records


@workspace_router.post(
    "",
    response_model=list[MaterialRecord],
    status_code=status.HTTP_201_CREATED,
)
async def upload_workspace_materials(
    workspace_id: str,
    request: Request,
    user: CurrentUser,
    files: Annotated[list[UploadFile], File()],
) -> list[MaterialRecord]:
    return await upload_materials(workspace_id, request, user, files)


@router.get("/search", response_model=list[SearchResult])
def search_materials(
    project_id: str,
    request: Request,
    user: CurrentUser,
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=8, ge=1, le=50),
) -> list[SearchResult]:
    _require_project(request, user.id, project_id)
    return request.app.state.knowledge.search(
        owner_id=user.id,
        project_id=project_id,
        query=q,
        limit=limit,
    )


@workspace_router.get("/search", response_model=list[SearchResult])
def search_workspace_materials(
    workspace_id: str,
    request: Request,
    user: CurrentUser,
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=8, ge=1, le=50),
) -> list[SearchResult]:
    return search_materials(workspace_id, request, user, q, limit)


@router.get("/{material_id}", response_model=MaterialRecord)
def material_status(
    project_id: str,
    material_id: str,
    request: Request,
    user: CurrentUser,
) -> MaterialRecord:
    _require_project(request, user.id, project_id)
    try:
        return request.app.state.knowledge.get_material(
            owner_id=user.id,
            project_id=project_id,
            material_id=material_id,
        )
    except MaterialNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "material_not_found", "message": "Material not found"},
        ) from error


@workspace_router.get("/{material_id}", response_model=MaterialRecord)
def workspace_material_status(
    workspace_id: str,
    material_id: str,
    request: Request,
    user: CurrentUser,
) -> MaterialRecord:
    return material_status(workspace_id, material_id, request, user)
