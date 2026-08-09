"""Authenticated material upload, status, and search endpoints."""

from __future__ import annotations

from dataclasses import replace
from functools import partial
from hashlib import sha256
from typing import Annotated, Literal
from urllib.parse import quote

from anyio import to_thread
from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from refineq.api.dependencies import CurrentUser
from refineq.integrations.ocr import OcrError
from refineq.knowledge.execution import SubprocessTimeoutError, extract_text_isolated
from refineq.knowledge.extract import (
    ExtractionLimits,
    MaterialExtractionError,
    MaterialExtractionLimitError,
)
from refineq.knowledge.index import (
    MaterialDocument,
    MaterialNotFoundError,
    MaterialQuotaExceededError,
    MaterialRecord,
    SearchResult,
)
from refineq.knowledge.policy import MaterialPolicy, MaterialPolicyError, UploadDescriptor
from refineq.operations.recovery import RecoveryLease
from refineq.storage.json_store import RecordNotFoundError

router = APIRouter(prefix="/projects/{project_id}/materials", tags=["materials"])
workspace_router = APIRouter(
    prefix="/workspaces/{workspace_id}/materials",
    tags=["materials"],
)
_policy = MaterialPolicy()


class MaterialUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=500)
    tags: list[str] | None = Field(default=None, max_length=12)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_tag in value:
            tag = raw_tag.strip()
            if not tag or len(tag) > 32:
                raise ValueError("tags must contain 1 to 32 characters")
            key = tag.casefold()
            if key not in seen:
                normalized.append(tag)
                seen.add(key)
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> MaterialUpdateRequest:
        if self.title is None and self.tags is None:
            raise ValueError("At least one metadata field is required")
        return self


class MaterialBulkDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("material_ids")
    @classmethod
    def unique_material_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("material_ids must be unique")
        return value


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


def _extraction_limits(request: Request) -> ExtractionLimits:
    settings = request.app.state.settings
    return ExtractionLimits(
        max_pdf_pages=settings.material_max_pdf_pages,
        max_docx_entries=settings.material_max_docx_entries,
        max_docx_expanded_bytes=settings.material_max_docx_expanded_bytes,
        max_docx_compression_ratio=settings.material_max_docx_compression_ratio,
        max_extracted_chars=settings.material_max_extracted_chars,
        max_processing_seconds=settings.material_extraction_timeout_seconds,
    )


def _raise_extraction_error(error: MaterialExtractionError) -> None:
    limited = isinstance(error, MaterialExtractionLimitError)
    raise HTTPException(
        status_code=(
            status.HTTP_413_CONTENT_TOO_LARGE if limited else status.HTTP_422_UNPROCESSABLE_CONTENT
        ),
        detail={
            "code": "material_extraction_limit" if limited else "material_extraction_failed",
            "message": str(error),
        },
    ) from error


def _store_and_index(
    request: Request,
    owner_id: str,
    documents: list[MaterialDocument],
    material_payloads: list[bytes],
) -> list[MaterialRecord]:
    settings = request.app.state.settings
    lease = RecoveryLease.acquire_wait(request.app.state.material_deletions.lease_path)
    if lease is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "material_mutation_busy",
                "message": "Another material operation is in progress",
            },
        )
    stored_objects = []
    try:
        project_id = documents[0].project_id
        _require_project(request, owner_id, project_id)
        indexed_documents: list[MaterialDocument] = []
        for document, payload in zip(documents, material_payloads, strict=True):
            stored = request.app.state.object_storage.put(
                owner_id=owner_id,
                workspace_id=document.project_id,
                material_id=document.material_id,
                filename=document.filename,
                payload=payload,
            )
            stored_objects.append(stored)
            indexed_documents.append(replace(document, storage_key=stored.key))
        return request.app.state.knowledge.add_documents_with_quota(
            owner_id=owner_id,
            documents=indexed_documents,
            max_count=settings.material_max_count_per_user,
            max_bytes=settings.material_max_bytes_per_user,
        )
    except Exception:
        for stored in reversed(stored_objects):
            stored.rollback()
        raise
    finally:
        lease.release()


def _raise_quota_error(error: MaterialQuotaExceededError) -> None:
    raise HTTPException(
        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        detail={"code": "material_quota", "message": str(error)},
    ) from error


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
    try:
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

        limits = _extraction_limits(request)
        extracted: list[str] = []
        for (_, payload), descriptor in zip(loaded, descriptors, strict=True):
            used_ocr = False
            try:
                text = await to_thread.run_sync(
                    partial(
                        extract_text_isolated,
                        descriptor.filename,
                        descriptor.content_type,
                        payload,
                        limits,
                    ),
                    abandon_on_cancel=False,
                )
            except SubprocessTimeoutError:
                _raise_extraction_error(
                    MaterialExtractionLimitError("Material extraction exceeded its time budget")
                )
            except MaterialExtractionError as error:
                use_ocr = (
                    not isinstance(error, MaterialExtractionLimitError)
                    and descriptor.filename.lower().endswith(".pdf")
                    and request.app.state.ocr.available()
                )
                if use_ocr:
                    try:
                        text = await to_thread.run_sync(
                            request.app.state.ocr.extract,
                            descriptor.filename,
                            descriptor.content_type,
                            payload,
                            abandon_on_cancel=False,
                        )
                        used_ocr = True
                    except OcrError as ocr_error:
                        _raise_extraction_error(MaterialExtractionError(str(ocr_error)))
                else:
                    _raise_extraction_error(error)
            if (
                not used_ocr
                and descriptor.filename.lower().endswith(".pdf")
                and request.app.state.ocr.available()
            ):
                try:
                    text = await to_thread.run_sync(
                        partial(
                            request.app.state.ocr.extract,
                            descriptor.filename,
                            descriptor.content_type,
                            payload,
                            local_text=text,
                        ),
                        abandon_on_cancel=False,
                    )
                except OcrError as ocr_error:
                    _raise_extraction_error(MaterialExtractionError(str(ocr_error)))
            extracted.append(text)

        documents: list[MaterialDocument] = []
        material_payloads: list[bytes] = []
        for (_, payload), descriptor, text in zip(loaded, descriptors, extracted, strict=True):
            material_id = f"material_{sha256(project_id.encode() + payload).hexdigest()[:20]}"
            material_payloads.append(payload)
            documents.append(
                MaterialDocument(
                    project_id=project_id,
                    material_id=material_id,
                    filename=descriptor.filename,
                    content_type=descriptor.content_type,
                    size=len(payload),
                    text=text,
                )
            )

        try:
            return await to_thread.run_sync(
                partial(
                    _store_and_index,
                    request,
                    user.id,
                    documents,
                    material_payloads,
                ),
                abandon_on_cancel=False,
            )
        except MaterialQuotaExceededError as error:
            _raise_quota_error(error)
    finally:
        for upload in files:
            await upload.close()


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
    indexed = await upload_materials(workspace_id, request, user, files)
    for material in indexed:
        if material.status == "indexed":
            request.app.state.workspace_learning_service.try_record_journey_event(
                user.id,
                workspace_id,
                name="material_searchable",
                idempotency_key=material.id,
                occurred_at=material.indexed_at,
                ref_id=material.id,
            )
    return indexed


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


@router.get("", response_model=list[MaterialRecord])
def list_materials(
    project_id: str,
    request: Request,
    user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    tag: str | None = Query(default=None, min_length=1, max_length=32),
    sort: Literal["newest", "oldest", "title", "size_desc"] = "newest",
) -> list[MaterialRecord]:
    _require_project(request, user.id, project_id)
    return request.app.state.knowledge.list_materials(
        owner_id=user.id,
        project_id=project_id,
        status=status_filter,
        tag=tag,
        sort=sort,
    )


@workspace_router.get("", response_model=list[MaterialRecord])
def list_workspace_materials(
    workspace_id: str,
    request: Request,
    user: CurrentUser,
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    tag: str | None = Query(default=None, min_length=1, max_length=32),
    sort: Literal["newest", "oldest", "title", "size_desc"] = "newest",
) -> list[MaterialRecord]:
    return list_materials(workspace_id, request, user, status_filter, tag, sort)


def _update_material(
    project_id: str,
    material_id: str,
    payload: MaterialUpdateRequest,
    request: Request,
    user: CurrentUser,
) -> MaterialRecord:
    _require_project(request, user.id, project_id)
    try:
        return request.app.state.knowledge.update_material_metadata(
            owner_id=user.id,
            project_id=project_id,
            material_id=material_id,
            title=payload.title,
            tags=payload.tags,
        )
    except MaterialNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "material_not_found", "message": "Material not found"},
        ) from error


@router.patch("/{material_id}", response_model=MaterialRecord)
def update_material(
    project_id: str,
    material_id: str,
    payload: MaterialUpdateRequest,
    request: Request,
    user: CurrentUser,
) -> MaterialRecord:
    return _update_material(project_id, material_id, payload, request, user)


@workspace_router.patch("/{material_id}", response_model=MaterialRecord)
def update_workspace_material(
    workspace_id: str,
    material_id: str,
    payload: MaterialUpdateRequest,
    request: Request,
    user: CurrentUser,
) -> MaterialRecord:
    return _update_material(workspace_id, material_id, payload, request, user)


def _bulk_delete_materials(
    project_id: str,
    payload: MaterialBulkDeleteRequest,
    request: Request,
    user: CurrentUser,
) -> Response:
    _require_project(request, user.id, project_id)
    try:
        pending = request.app.state.material_deletions.prepare(
            owner_id=user.id,
            project_id=project_id,
            material_ids=payload.material_ids,
        )
        request.app.state.material_deletions.complete(pending)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except (MaterialNotFoundError, FileNotFoundError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "material_not_found", "message": "Material not found"},
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "material_bulk_delete_failed",
                "message": "Selected materials could not be deleted safely",
            },
        ) from error


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def bulk_delete_materials(
    project_id: str,
    payload: MaterialBulkDeleteRequest,
    request: Request,
    user: CurrentUser,
) -> Response:
    return _bulk_delete_materials(project_id, payload, request, user)


@workspace_router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def bulk_delete_workspace_materials(
    workspace_id: str,
    payload: MaterialBulkDeleteRequest,
    request: Request,
    user: CurrentUser,
) -> Response:
    return _bulk_delete_materials(workspace_id, payload, request, user)


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


def _download_material(
    project_id: str,
    material_id: str,
    request: Request,
    user: CurrentUser,
) -> Response:
    record = material_status(project_id, material_id, request, user)
    try:
        storage_key = request.app.state.knowledge.get_material_storage_key(
            owner_id=user.id,
            project_id=project_id,
            material_id=material_id,
        )
        payload = request.app.state.object_storage.get(storage_key)
    except (MaterialNotFoundError, FileNotFoundError) as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "material_not_found", "message": "Material not found"},
        ) from error
    escaped = record.filename.replace('"', "")
    disposition = f"attachment; filename=\"{escaped}\"; filename*=UTF-8''{quote(record.filename)}"
    return Response(
        content=payload,
        media_type=record.content_type,
        headers={"Content-Disposition": disposition},
    )


@router.get("/{material_id}/download")
def download_material(
    project_id: str,
    material_id: str,
    request: Request,
    user: CurrentUser,
) -> Response:
    return _download_material(project_id, material_id, request, user)


@workspace_router.get("/{material_id}/download")
def download_workspace_material(
    workspace_id: str,
    material_id: str,
    request: Request,
    user: CurrentUser,
) -> Response:
    return _download_material(workspace_id, material_id, request, user)


def _delete_material(
    project_id: str,
    material_id: str,
    request: Request,
    user: CurrentUser,
) -> Response:
    return _bulk_delete_materials(
        project_id,
        MaterialBulkDeleteRequest(material_ids=[material_id]),
        request,
        user,
    )


@router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_material(
    project_id: str,
    material_id: str,
    request: Request,
    user: CurrentUser,
) -> Response:
    return _delete_material(project_id, material_id, request, user)


@workspace_router.delete("/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace_material(
    workspace_id: str,
    material_id: str,
    request: Request,
    user: CurrentUser,
) -> Response:
    return _delete_material(workspace_id, material_id, request, user)
