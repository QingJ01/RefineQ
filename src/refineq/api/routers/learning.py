"""Authenticated learning-journey endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status

from refineq.api.dependencies import CurrentUser
from refineq.learning.models import LearningEvidence, LearningMode, StudyPlan, StudySession
from refineq.learning.service import (
    AnswerRequest,
    AnswerResponse,
    DiagnosticRequest,
    LearningConflictError,
    LearningNotSeededError,
    LearningServiceError,
    PlanSessionUpdate,
    ProgressResponse,
    ProjectNotFoundError,
    QuestionResponse,
    QuestionSaveRequest,
    SavedQuestionResponse,
    SeedRequest,
)

router = APIRouter(prefix="/projects/{project_id}/learning", tags=["learning"])
workspace_router = APIRouter(
    prefix="/workspaces/{workspace_id}/learning",
    tags=["learning"],
)


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
def question(
    project_id: str,
    request: Request,
    user: CurrentUser,
    topic_id: str | None = None,
    difficulty: int | None = Query(default=None, ge=1, le=5),
    mode: LearningMode = LearningMode.CONCEPT,
    replace: bool = False,
) -> QuestionResponse:
    try:
        return request.app.state.learning_service.next_question(
            user.id,
            project_id,
            topic_id=topic_id,
            difficulty_level=difficulty,
            learning_mode=mode,
            replace_pending=replace,
        )
    except LearningServiceError as error:
        _raise_api_error(error)


@workspace_router.get("/question", response_model=QuestionResponse)
def workspace_question(
    workspace_id: str,
    request: Request,
    user: CurrentUser,
    topic_id: str | None = None,
    difficulty: int | None = Query(default=None, ge=1, le=5),
    mode: LearningMode = LearningMode.CONCEPT,
    replace: bool = False,
) -> QuestionResponse:
    try:
        return request.app.state.workspace_learning_service.next_question(
            user.id,
            workspace_id,
            topic_id=topic_id,
            difficulty_level=difficulty,
            learning_mode=mode,
            replace_pending=replace,
        )
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


@workspace_router.post("/answer", response_model=AnswerResponse)
def workspace_answer(
    workspace_id: str,
    payload: AnswerRequest,
    request: Request,
    user: CurrentUser,
) -> AnswerResponse:
    try:
        return request.app.state.workspace_learning_service.submit_answer(
            user.id,
            workspace_id,
            payload,
        )
    except LearningServiceError as error:
        _raise_api_error(error)


@workspace_router.get(
    "/questions/saved",
    response_model=list[SavedQuestionResponse],
)
def saved_workspace_questions(
    workspace_id: str,
    request: Request,
    user: CurrentUser,
) -> list[SavedQuestionResponse]:
    try:
        return request.app.state.workspace_learning_service.saved_questions(
            user.id,
            workspace_id,
        )
    except LearningServiceError as error:
        _raise_api_error(error)


@workspace_router.put(
    "/questions/{question_id}/saved",
    response_model=SavedQuestionResponse,
)
def save_workspace_question(
    workspace_id: str,
    question_id: str,
    payload: QuestionSaveRequest,
    request: Request,
    user: CurrentUser,
) -> SavedQuestionResponse:
    try:
        return request.app.state.workspace_learning_service.set_question_saved(
            user.id,
            workspace_id,
            question_id,
            payload,
        )
    except LearningServiceError as error:
        _raise_api_error(error)


@workspace_router.patch(
    "/plan/sessions/{session_id}",
    response_model=StudySession,
)
def update_workspace_plan_session(
    workspace_id: str,
    session_id: str,
    payload: PlanSessionUpdate,
    request: Request,
    user: CurrentUser,
) -> StudySession:
    try:
        return request.app.state.workspace_learning_service.update_plan_session(
            user.id,
            workspace_id,
            session_id,
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
