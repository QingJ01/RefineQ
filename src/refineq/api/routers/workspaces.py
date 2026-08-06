"""Authenticated APIs for automatic personal learning spaces."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from refineq.api.dependencies import CurrentUser
from refineq.learning.service import LearningServiceError
from refineq.workspaces.models import LearningWorkspace
from refineq.workspaces.service import (
    WorkspaceConstraintError,
    WorkspaceNotFoundError,
    WorkspaceQuotaError,
    WorkspaceResolveRequest,
    WorkspaceRouteResponse,
    WorkspaceServiceError,
    WorkspaceSnapshot,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _raise_workspace_error(error: Exception, status_code: int, code: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(error)},
    ) from error


@router.get("", response_model=list[LearningWorkspace])
def list_workspaces(request: Request, user: CurrentUser) -> list[LearningWorkspace]:
    return request.app.state.workspace_service.list(user.id)


@router.post("/resolve", response_model=WorkspaceRouteResponse)
def resolve_workspace(
    payload: WorkspaceResolveRequest,
    request: Request,
    user: CurrentUser,
) -> WorkspaceRouteResponse:
    try:
        return request.app.state.workspace_service.resolve(user.id, payload)
    except WorkspaceConstraintError as error:
        _raise_workspace_error(
            error,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            error.code,
        )
    except WorkspaceQuotaError as error:
        _raise_workspace_error(error, status.HTTP_409_CONFLICT, error.code)
    except LearningServiceError as error:
        _raise_workspace_error(error, status.HTTP_409_CONFLICT, error.code)
    except WorkspaceServiceError as error:
        _raise_workspace_error(error, status.HTTP_500_INTERNAL_SERVER_ERROR, error.code)


@router.get("/{workspace_id}/snapshot", response_model=WorkspaceSnapshot)
def workspace_snapshot(
    workspace_id: str,
    request: Request,
    user: CurrentUser,
) -> WorkspaceSnapshot:
    try:
        return request.app.state.workspace_service.snapshot(user.id, workspace_id)
    except WorkspaceNotFoundError as error:
        _raise_workspace_error(error, status.HTTP_404_NOT_FOUND, error.code)
