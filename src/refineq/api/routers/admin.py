"""Administrator-only system overview and integration configuration."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict

from refineq.api.dependencies import AdminUser
from refineq.integrations.models import (
    IntegrationKind,
    IntegrationTestResult,
    IntegrationUpdate,
    PublicIntegrationSettings,
)
from refineq.integrations.repository import IntegrationNotConfiguredError

router = APIRouter(prefix="/admin", tags=["admin"])


class AdminOverview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    database: str
    pgvector: bool
    users: int
    integrations_configured: int


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
