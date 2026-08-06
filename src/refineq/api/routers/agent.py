"""Authenticated project-Agent conversation endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from refineq.agent.service import (
    AgentChatRequest,
    AgentChatResponse,
    AgentLearningStateError,
    AgentProjectNotFoundError,
    AgentServiceError,
    AgentSessionConflictError,
)
from refineq.agent.settings import ModelNotConfiguredError
from refineq.api.dependencies import CurrentUser

router = APIRouter(prefix="/projects/{project_id}/agent", tags=["agent"])


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
    except (AgentLearningStateError, AgentSessionConflictError) as error:
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
