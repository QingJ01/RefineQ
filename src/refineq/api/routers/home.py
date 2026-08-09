"""Authenticated home supervisor dispatch and confirmation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from refineq.api.dependencies import CurrentUser
from refineq.home.models import (
    HomeActionReceipt,
    HomeCancelRequest,
    HomeConfirmRequest,
    HomeDispatchRequest,
    HomeDispatchResult,
    HomeProposalRevisionRequest,
    WorkspaceProposal,
)
from refineq.home.service import (
    HomeActionConflictError,
    HomeConfirmationError,
    HomeServiceError,
)

router = APIRouter(prefix="/home", tags=["home"])


def _raise(error: Exception, status_code: int, code: str) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": str(error)},
    ) from error


@router.post("/dispatch", response_model=HomeDispatchResult)
def dispatch_home(
    payload: HomeDispatchRequest,
    request: Request,
    user: CurrentUser,
) -> HomeDispatchResult:
    try:
        return request.app.state.home_dispatch.dispatch(
            user.id,
            payload,
            is_admin=user.role == "admin",
        )
    except HomeConfirmationError as error:
        _raise(error, status.HTTP_422_UNPROCESSABLE_CONTENT, error.code)
    except HomeActionConflictError as error:
        _raise(error, status.HTTP_409_CONFLICT, error.code)
    except HomeServiceError as error:
        _raise(error, status.HTTP_500_INTERNAL_SERVER_ERROR, error.code)


@router.post("/actions/confirm", response_model=HomeActionReceipt)
def confirm_home_action(
    payload: HomeConfirmRequest,
    request: Request,
    user: CurrentUser,
) -> HomeActionReceipt:
    try:
        return request.app.state.home_dispatch.confirm(user.id, payload)
    except HomeConfirmationError as error:
        _raise(error, status.HTTP_422_UNPROCESSABLE_CONTENT, error.code)
    except HomeActionConflictError as error:
        _raise(error, status.HTTP_409_CONFLICT, error.code)
    except HomeServiceError as error:
        _raise(error, status.HTTP_500_INTERNAL_SERVER_ERROR, error.code)


@router.post("/actions/revise", response_model=WorkspaceProposal)
def revise_home_proposal(
    payload: HomeProposalRevisionRequest,
    request: Request,
    user: CurrentUser,
) -> WorkspaceProposal:
    try:
        return request.app.state.home_dispatch.revise_workspace_proposal(user.id, payload)
    except HomeConfirmationError as error:
        _raise(error, status.HTTP_422_UNPROCESSABLE_CONTENT, error.code)
    except HomeActionConflictError as error:
        _raise(error, status.HTTP_409_CONFLICT, error.code)
    except HomeServiceError as error:
        _raise(error, status.HTTP_500_INTERNAL_SERVER_ERROR, error.code)


@router.post("/actions/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_home_action(
    payload: HomeCancelRequest,
    request: Request,
    user: CurrentUser,
) -> Response:
    request.app.state.home_dispatch.cancel_proposal(user.id, payload.request_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
