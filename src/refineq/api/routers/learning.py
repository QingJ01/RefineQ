"""Authenticated learning-journey endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from refineq.api.dependencies import CurrentUser
from refineq.learning.models import LearningEvidence, StudyPlan
from refineq.learning.service import (
    AnswerRequest,
    AnswerResponse,
    DiagnosticRequest,
    LearningConflictError,
    LearningNotSeededError,
    LearningServiceError,
    ProgressResponse,
    ProjectNotFoundError,
    QuestionResponse,
    SeedRequest,
)

router = APIRouter(prefix="/projects/{project_id}/learning", tags=["learning"])


def _raise_api_error(error: LearningServiceError) -> None:
    if isinstance(error, ProjectNotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, (LearningNotSeededError, LearningConflictError)):
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    raise HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": str(error)},
    ) from error


@router.post("/seed", response_model=ProgressResponse)
def seed(
    project_id: str,
    payload: SeedRequest,
    request: Request,
    user: CurrentUser,
) -> ProgressResponse:
    try:
        return request.app.state.learning_service.seed(user.id, project_id, payload)
    except LearningServiceError as error:
        _raise_api_error(error)


@router.post("/diagnostic", response_model=ProgressResponse)
def diagnose(
    project_id: str,
    payload: DiagnosticRequest,
    request: Request,
    user: CurrentUser,
) -> ProgressResponse:
    try:
        return request.app.state.learning_service.diagnose(user.id, project_id, payload)
    except LearningServiceError as error:
        _raise_api_error(error)


@router.post("/plan", response_model=StudyPlan)
def create_plan(project_id: str, request: Request, user: CurrentUser) -> StudyPlan:
    try:
        return request.app.state.learning_service.create_plan(user.id, project_id)
    except LearningServiceError as error:
        _raise_api_error(error)


@router.get("/question", response_model=QuestionResponse)
def question(project_id: str, request: Request, user: CurrentUser) -> QuestionResponse:
    try:
        return request.app.state.learning_service.next_question(user.id, project_id)
    except LearningServiceError as error:
        _raise_api_error(error)


@router.post("/answer", response_model=AnswerResponse)
def answer(
    project_id: str,
    payload: AnswerRequest,
    request: Request,
    user: CurrentUser,
) -> AnswerResponse:
    try:
        return request.app.state.learning_service.submit_answer(
            user.id,
            project_id,
            payload,
        )
    except LearningServiceError as error:
        _raise_api_error(error)


@router.get("/progress", response_model=ProgressResponse)
def progress(project_id: str, request: Request, user: CurrentUser) -> ProgressResponse:
    try:
        return request.app.state.learning_service.progress(user.id, project_id)
    except LearningServiceError as error:
        _raise_api_error(error)


@router.get("/evidence", response_model=list[LearningEvidence])
def evidence(
    project_id: str,
    request: Request,
    user: CurrentUser,
) -> list[LearningEvidence]:
    try:
        return request.app.state.learning_service.evidence(user.id, project_id)
    except LearningServiceError as error:
        _raise_api_error(error)
