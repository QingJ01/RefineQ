"""Authenticated project-Agent conversation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from refineq.agent.service import (
    AgentChatRequest,
    AgentChatResponse,
    AgentLearningStateError,
    AgentProjectNotFoundError,
    AgentServiceError,
    AgentSessionConflictError,
    AgentSessionDetail,
    AgentSessionLimitError,
    AgentSessionNotFoundError,
    AgentSessionSummary,
)
from refineq.agent.settings import ModelNotConfiguredError
from refineq.api.dependencies import CurrentUser

router = APIRouter(prefix="/projects/{project_id}/agent", tags=["agent"])
workspace_router = APIRouter(
    prefix="/workspaces/{workspace_id}/agent",
    tags=["agent"],
)


def _raise_agent_error(error: Exception, *, status_code: int, code: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(error)},
    ) from error


@router.post("/chat", response_model=AgentChatResponse)
def chat(
    project_id: str,
    payload: AgentChatRequest,
    request: Request,
    user: CurrentUser,
) -> AgentChatResponse:
    try:
        return request.app.state.agent.chat(user.id, project_id, payload)
    except AgentProjectNotFoundError as error:
        _raise_agent_error(
            error,
            status_code=status.HTTP_404_NOT_FOUND,
            code=error.code,
        )
    except (
        AgentLearningStateError,
        AgentSessionConflictError,
        AgentSessionLimitError,
    ) as error:
        _raise_agent_error(
            error,
            status_code=status.HTTP_409_CONFLICT,
            code=error.code,
        )
    except ModelNotConfiguredError as error:
        _raise_agent_error(
            error,
            status_code=status.HTTP_409_CONFLICT,
            code="model_not_configured",
        )
    except AgentServiceError as error:
        _raise_agent_error(
            error,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=error.code,
        )


@workspace_router.post("/chat", response_model=AgentChatResponse)
def workspace_chat(
    workspace_id: str,
    payload: AgentChatRequest,
    request: Request,
    user: CurrentUser,
) -> AgentChatResponse:
    try:
        return request.app.state.workspace_agent.chat(user.id, workspace_id, payload)
    except AgentProjectNotFoundError as error:
        _raise_agent_error(error, status_code=status.HTTP_404_NOT_FOUND, code="workspace_not_found")
    except (
        AgentLearningStateError,
        AgentSessionConflictError,
        AgentSessionLimitError,
    ) as error:
        _raise_agent_error(error, status_code=status.HTTP_409_CONFLICT, code=error.code)
    except ModelNotConfiguredError as error:
        _raise_agent_error(
            error,
            status_code=status.HTTP_409_CONFLICT,
            code="model_not_configured",
        )
    except AgentServiceError as error:
        _raise_agent_error(
            error,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code=error.code,
        )


@workspace_router.get("/sessions", response_model=list[AgentSessionSummary])
def list_workspace_sessions(
    workspace_id: str,
    request: Request,
    user: CurrentUser,
) -> list[AgentSessionSummary]:
    try:
        return request.app.state.workspace_agent.list_sessions(user.id, workspace_id)
    except AgentProjectNotFoundError as error:
        _raise_agent_error(
            error,
            status_code=status.HTTP_404_NOT_FOUND,
            code="workspace_not_found",
        )


@workspace_router.get("/sessions/{session_id}", response_model=AgentSessionDetail)
def get_workspace_session(
    workspace_id: str,
    session_id: str,
    request: Request,
    user: CurrentUser,
) -> AgentSessionDetail:
    try:
        return request.app.state.workspace_agent.get_session(
            user.id,
            workspace_id,
            session_id,
        )
    except AgentProjectNotFoundError as error:
        _raise_agent_error(
            error,
            status_code=status.HTTP_404_NOT_FOUND,
            code="workspace_not_found",
        )
    except AgentSessionNotFoundError as error:
        _raise_agent_error(
            error,
            status_code=status.HTTP_404_NOT_FOUND,
            code=error.code,
        )


@workspace_router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_workspace_session(
    workspace_id: str,
    session_id: str,
    request: Request,
    user: CurrentUser,
) -> Response:
    try:
        request.app.state.workspace_agent.delete_session(
            user.id,
            workspace_id,
            session_id,
        )
    except AgentProjectNotFoundError as error:
        _raise_agent_error(
            error,
            status_code=status.HTTP_404_NOT_FOUND,
            code="workspace_not_found",
        )
    except AgentSessionNotFoundError as error:
        _raise_agent_error(
            error,
            status_code=status.HTTP_404_NOT_FOUND,
            code=error.code,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
