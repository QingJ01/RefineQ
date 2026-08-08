"""Authenticated APIs for automatic personal learning spaces."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from refineq.api.dependencies import CurrentUser
from refineq.learning.service import LearningServiceError
from refineq.workspaces.models import LearningWorkspace
from refineq.workspaces.service import (
    TopicSuggestion,
    TopicSuggestionNotFoundError,
    WorkspaceConflictError,
    WorkspaceConstraintError,
    WorkspaceNotFoundError,
    WorkspaceQuotaError,
    WorkspaceResolveRequest,
    WorkspaceRouteResponse,
    WorkspaceServiceError,
    WorkspaceSnapshot,
    WorkspaceUpdateRequest,
)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _raise_workspace_error(error: Exception, status_code: int, code: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(error)},
    ) from error


@router.get("", response_model=list[LearningWorkspace])
def list_workspaces(
    request: Request,
    user: CurrentUser,
    include_archived: bool = False,
) -> list[LearningWorkspace]:
    return request.app.state.workspace_service.list(
        user.id,
        include_archived=include_archived,
    )


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
    except WorkspaceConflictError as error:
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


@router.get("/{workspace_id}/topic-suggestions", response_model=list[TopicSuggestion])
def workspace_topic_suggestions(
    workspace_id: str,
    request: Request,
    user: CurrentUser,
) -> list[TopicSuggestion]:
    try:
        return request.app.state.workspace_service.topic_suggestions(user.id, workspace_id)
    except WorkspaceNotFoundError as error:
        _raise_workspace_error(error, status.HTTP_404_NOT_FOUND, error.code)


@router.post(
    "/{workspace_id}/topic-suggestions/{suggestion_id}/accept",
    response_model=WorkspaceSnapshot,
)
def accept_workspace_topic_suggestion(
    workspace_id: str,
    suggestion_id: str,
    request: Request,
    user: CurrentUser,
) -> WorkspaceSnapshot:
    try:
        return request.app.state.workspace_service.accept_topic_suggestion(
            user.id,
            workspace_id,
            suggestion_id,
        )
    except (WorkspaceNotFoundError, TopicSuggestionNotFoundError) as error:
        _raise_workspace_error(error, status.HTTP_404_NOT_FOUND, error.code)
    except LearningServiceError as error:
        _raise_workspace_error(error, status.HTTP_409_CONFLICT, error.code)


@router.patch("/{workspace_id}", response_model=LearningWorkspace)
def update_workspace(
    workspace_id: str,
    payload: WorkspaceUpdateRequest,
    request: Request,
    user: CurrentUser,
) -> LearningWorkspace:
    try:
        return request.app.state.workspace_service.update(user.id, workspace_id, payload)
    except WorkspaceNotFoundError as error:
        _raise_workspace_error(error, status.HTTP_404_NOT_FOUND, error.code)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(workspace_id: str, request: Request, user: CurrentUser) -> Response:
    try:
        request.app.state.workspace_service.delete(user.id, workspace_id)
    except WorkspaceNotFoundError as error:
        _raise_workspace_error(error, status.HTTP_404_NOT_FOUND, error.code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
