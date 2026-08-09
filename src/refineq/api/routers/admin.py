"""Administrator-only system overview and integration configuration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from refineq.api.dependencies import AdminUser
from refineq.integrations.models import (
    IntegrationKind,
    IntegrationTestResult,
    IntegrationUpdate,
    PublicIntegrationSettings,
)
from refineq.integrations.repository import IntegrationNotConfiguredError
from refineq.operations.admin import RestoreConfirmationError
from refineq.operations.backup import BackupError, ManagedBackupNotFoundError

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


class AdminOverview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    database: str
    pgvector: bool
    users: int
    integrations_configured: int


class QuotaValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    materials: int
    material_bytes: int
    workspaces: int


class AdminUserSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    email: str
    display_name: str
    role: Literal["learner", "admin"]
    created_at: datetime
    usage: QuotaValues
    quotas: QuotaValues


class AdminUsersPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[AdminUserSummary]
    page: int
    page_size: int
    total: int
    pages: int


class AdminJobSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Literal["material_index", "embedding_backfill"]
    status: Literal["idle", "pending"]
    pending: int
    completed: int
    failed: int
    total: int
    last_activity_at: datetime | None


class AdminJobsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[AdminJobSummary]
    observed_at: datetime


class DurationPercentiles(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_size: int = Field(ge=0)
    p50: float | None = Field(default=None, ge=0)
    p90: float | None = Field(default=None, ge=0)


class LearningMetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    starts_at: datetime
    ends_at: datetime
    active_learners: int = Field(ge=0)
    grounded_loop_completers: int = Field(ge=0)
    grounded_loop_completion_rate: float = Field(ge=0, le=1)
    intent_to_grounded_grade_seconds: DurationPercentiles
    revisit_open_to_question_seconds: DurationPercentiles


class AuditEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    actor_id: str
    actor_email: str
    action: str
    target: str
    details: dict[str, Any]
    created_at: datetime


class AuditPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[AuditEntry]
    page: int
    page_size: int
    total: int
    pages: int


class ManagedBackupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    created_at: datetime
    size: int
    file_count: int
    total_bytes: int


class ManagedBackupsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[ManagedBackupResponse]
    total: int


class RestoreValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: str = Field(min_length=1, max_length=200)


class RestoreValidationResponse(ManagedBackupResponse):
    status: Literal["validated"] = "validated"


@router.get("/overview", response_model=AdminOverview)
def overview(request: Request, admin: AdminUser) -> AdminOverview:
    del admin
    database = request.app.state.database
    return AdminOverview(
        database="postgresql" if database.is_postgresql else "sqlite",
        pgvector=database.is_postgresql,
        users=request.app.state.identity.count_users(),
        integrations_configured=request.app.state.integrations.count_configured(),
    )


@router.get("/users", response_model=AdminUsersPage)
def list_users(
    request: Request,
    admin: AdminUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AdminUsersPage:
    del admin
    return AdminUsersPage.model_validate(
        request.app.state.admin_operations.list_users(page=page, page_size=page_size)
    )


@router.get("/jobs", response_model=AdminJobsResponse)
def list_jobs(request: Request, admin: AdminUser) -> AdminJobsResponse:
    del admin
    return AdminJobsResponse.model_validate(request.app.state.admin_operations.jobs())


@router.get("/metrics/learning", response_model=LearningMetricsResponse)
def learning_metrics(
    request: Request,
    admin: AdminUser,
    starts_at: Annotated[datetime, Query()],
    ends_at: Annotated[datetime, Query()],
) -> LearningMetricsResponse:
    del admin
    try:
        if ends_at - starts_at > timedelta(days=31):
            raise ValueError("Metric windows cannot exceed 31 days")
        return LearningMetricsResponse.model_validate(
            request.app.state.admin_operations.learning_metrics(
                starts_at=starts_at,
                ends_at=ends_at,
            )
        )
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_metric_range", "message": str(error)},
        ) from error


@router.get("/audit", response_model=AuditPage)
def list_audit(
    request: Request,
    admin: AdminUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AuditPage:
    del admin
    return AuditPage.model_validate(
        request.app.state.admin_operations.list_audit(page=page, page_size=page_size)
    )


@router.post(
    "/backups",
    response_model=ManagedBackupResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_backup(request: Request, admin: AdminUser) -> ManagedBackupResponse:
    try:
        return ManagedBackupResponse.model_validate(
            request.app.state.admin_operations.create_backup(actor_id=admin.id),
            from_attributes=True,
        )
    except BackupError as error:
        logger.exception("Managed backup creation failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "backup_creation_failed",
                "message": "Backup could not be created safely.",
            },
        ) from error


@router.get("/backups", response_model=ManagedBackupsResponse)
def list_admin_backups(request: Request, admin: AdminUser) -> ManagedBackupsResponse:
    del admin
    try:
        backups = request.app.state.admin_operations.list_backups()
    except BackupError as error:
        logger.exception("Managed backup listing failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "backup_listing_failed",
                "message": "Backups could not be listed safely.",
            },
        ) from error
    return ManagedBackupsResponse(
        items=[
            ManagedBackupResponse.model_validate(item, from_attributes=True) for item in backups
        ],
        total=len(backups),
    )


@router.post(
    "/backups/{backup_id}/restore-validation",
    response_model=RestoreValidationResponse,
)
def validate_admin_restore(
    backup_id: str,
    payload: RestoreValidationRequest,
    request: Request,
    admin: AdminUser,
) -> RestoreValidationResponse:
    try:
        backup = request.app.state.admin_operations.validate_restore(
            backup_id,
            confirmation=payload.confirmation,
            actor_id=admin.id,
        )
    except RestoreConfirmationError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "restore_confirmation_required", "message": str(error)},
        ) from error
    except ManagedBackupNotFoundError as error:
        logger.info("Managed restore validation requested an unavailable backup")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "backup_not_found",
                "message": "The requested backup is unavailable.",
            },
        ) from error
    except BackupError as error:
        logger.exception("Managed restore validation failed")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "backup_invalid",
                "message": "Backup integrity validation failed.",
            },
        ) from error
    public = ManagedBackupResponse.model_validate(backup, from_attributes=True)
    return RestoreValidationResponse.model_validate({"status": "validated", **public.model_dump()})


@router.get("/integrations", response_model=list[PublicIntegrationSettings])
def list_integrations(request: Request, admin: AdminUser) -> list[PublicIntegrationSettings]:
    del admin
    return request.app.state.integrations.list_public()


@router.put("/integrations/{kind}", response_model=PublicIntegrationSettings)
def update_integration(
    kind: IntegrationKind,
    payload: IntegrationUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    admin: AdminUser,
) -> PublicIntegrationSettings:
    try:
        updated = request.app.state.integrations.save(kind, payload, actor_id=admin.id)
        if kind is IntegrationKind.EMBEDDING and payload.enabled:
            background_tasks.add_task(request.app.state.knowledge.backfill_embeddings)
        return updated
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_integration", "message": str(error)},
        ) from error


@router.post("/integrations/{kind}/test", response_model=IntegrationTestResult)
def test_integration(
    kind: IntegrationKind,
    request: Request,
    admin: AdminUser,
) -> IntegrationTestResult:
    try:
        return request.app.state.integration_tester.test(kind, actor_id=admin.id)
    except IntegrationNotConfiguredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "integration_not_configured", "message": str(error)},
        ) from error
