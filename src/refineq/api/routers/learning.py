"""Authenticated learning-journey endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from refineq.api.dependencies import CurrentUser
from refineq.learning.models import LearningEvidence, StudyPlan, StudySession
from refineq.learning.personalized import TargetedPlanRequest
from refineq.learning.service import (
    AnswerRequest,
    AnswerResponse,
    DiagnosticRequest,
    LearningConflictError,
    LearningNotSeededError,
    LearningServiceError,
    PlanSessionCreate,
    PlanSessionUpdate,
    ProgressResponse,
    ProjectNotFoundError,
    QuestionNotFoundError,
    QuestionRequest,
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
    if isinstance(error, (ProjectNotFoundError, QuestionNotFoundError)):
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


@workspace_router.post("/plan/targeted", response_model=StudyPlan)
def create_targeted_plan(
    workspace_id: str,
    payload: TargetedPlanRequest,
    request: Request,
    user: CurrentUser,
) -> StudyPlan:
    try:
        request.app.state.workspaces.get(user.id, workspace_id)
        return request.app.state.targeted_plans.generate(user.id, workspace_id, payload)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "invalid_targeted_plan", "message": str(error)},
        ) from error


@router.post("/question", response_model=QuestionResponse)
def create_question(
    project_id: str,
    payload: QuestionRequest,
    request: Request,
    user: CurrentUser,
) -> QuestionResponse:
    try:
        return request.app.state.learning_service.next_question(
            user.id,
            project_id,
            topic_id=payload.topic_id,
            difficulty_level=payload.difficulty,
            learning_mode=payload.mode,
            replace_pending=payload.replace,
            request_id=payload.request_id,
        )
    except LearningServiceError as error:
        _raise_api_error(error)


@workspace_router.post("/question", response_model=QuestionResponse)
def create_workspace_question(
    workspace_id: str,
    payload: QuestionRequest,
    request: Request,
    user: CurrentUser,
) -> QuestionResponse:
    try:
        return request.app.state.workspace_learning_service.next_question(
            user.id,
            workspace_id,
            topic_id=payload.topic_id,
            difficulty_level=payload.difficulty,
            learning_mode=payload.mode,
            replace_pending=payload.replace,
            request_id=payload.request_id,
        )
    except LearningServiceError as error:
        _raise_api_error(error)


@router.get("/question", response_model=QuestionResponse)
def pending_question(
    project_id: str,
    request: Request,
    user: CurrentUser,
) -> QuestionResponse:
    try:
        return request.app.state.learning_service.pending_question(user.id, project_id)
    except LearningServiceError as error:
        _raise_api_error(error)


@workspace_router.get("/question", response_model=QuestionResponse)
def pending_workspace_question(
    workspace_id: str,
    request: Request,
    user: CurrentUser,
) -> QuestionResponse:
    try:
        return request.app.state.workspace_learning_service.pending_question(user.id, workspace_id)
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


@workspace_router.post("/plan/sessions", response_model=StudySession)
def add_workspace_plan_session(
    workspace_id: str, payload: PlanSessionCreate, request: Request, user: CurrentUser
) -> StudySession:
    try:
        return request.app.state.workspace_learning_service.add_plan_session(
            user.id, workspace_id, payload
        )
    except LearningServiceError as error:
        _raise_api_error(error)


@workspace_router.delete("/plan", status_code=status.HTTP_204_NO_CONTENT)
def clear_workspace_plan(workspace_id: str, request: Request, user: CurrentUser) -> None:
    try:
        request.app.state.workspace_learning_service.clear_plan(user.id, workspace_id)
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
