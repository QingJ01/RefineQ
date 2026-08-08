"""Local registration, login, and current-user endpoints."""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response, status

from refineq.api.dependencies import CurrentUser
from refineq.identity.models import (
    AccountDeleteRequest,
    AccountExportResponse,
    AuthCapabilities,
    AuthResponse,
    LoginRequest,
    PasswordChangeRequest,
    PasswordResetAccepted,
    PasswordResetComplete,
    PasswordResetRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    User,
)
from refineq.identity.service import (
    AccountDeletionError,
    AccountExistsError,
    InvalidCredentialsError,
    InvalidResetTokenError,
)

router = APIRouter(prefix="/auth", tags=["identity"])
logger = logging.getLogger(__name__)


def _auth_response(request: Request, user: User) -> AuthResponse:
    return AuthResponse(
        access_token=request.app.state.identity.issue_token(user),
        user=user,
    )


def _deliver_password_reset(delivery, email: str, token: str) -> None:
    try:
        delivery.send(email, token)
    except Exception as error:  # pragma: no cover - provider-specific failures
        logger.warning("Password reset delivery failed: %s", type(error).__name__)


@router.get("/capabilities", response_model=AuthCapabilities)
def auth_capabilities(request: Request) -> AuthCapabilities:
    return AuthCapabilities(
        password_reset_available=(
            request.app.state.settings.password_reset_expose_token
            or request.app.state.password_reset_delivery.enabled
        )
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request) -> AuthResponse:
    try:
        user = request.app.state.identity.register(
            email=payload.email,
            password=payload.password.get_secret_value(),
            display_name=payload.display_name,
        )
    except AccountExistsError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "validation_error", "message": "Request validation failed"},
        ) from error
    return _auth_response(request, user)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request) -> AuthResponse:
    try:
        user, access_token = request.app.state.identity.authenticate_with_token(
            email=payload.email,
            password=payload.password.get_secret_value(),
        )
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": str(error)},
        ) from error
    return AuthResponse(access_token=access_token, user=user)


@router.get("/me", response_model=User)
def me(user: CurrentUser) -> User:
    return user


@router.patch("/profile", response_model=User)
def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    user: CurrentUser,
) -> User:
    return request.app.state.identity.update_profile(
        user.id,
        display_name=payload.display_name,
    )


@router.put("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    user: CurrentUser,
) -> Response:
    try:
        request.app.state.identity.change_password(
            user.id,
            current_password=payload.current_password.get_secret_value(),
            new_password=payload.new_password.get_secret_value(),
        )
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": str(error)},
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/export", response_model=AccountExportResponse)
def export_account(
    response: Response,
    request: Request,
    user: CurrentUser,
) -> AccountExportResponse:
    response.headers["Content-Disposition"] = 'attachment; filename="refineq-account-export.json"'
    return request.app.state.identity.export_account(user)


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
def revoke_sessions(request: Request, user: CurrentUser) -> Response:
    request.app.state.identity.revoke_sessions(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    payload: AccountDeleteRequest,
    request: Request,
    user: CurrentUser,
) -> Response:
    current_password = payload.current_password.get_secret_value()
    if payload.confirmation.strip().lower() != user.email:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "account_confirmation_mismatch",
                "message": "Type the account email to confirm deletion",
            },
        )

    try:
        pending = request.app.state.account_deletions.prepare(
            user.id,
            current_password=current_password,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": str(error)},
        ) from error
    except AccountDeletionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "account_deletion_blocked", "message": str(error)},
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "account_deletion_failed",
                "message": "Account deletion could not be completed safely",
            },
        ) from error
    try:
        request.app.state.account_deletions.complete(
            pending,
            current_password=current_password,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": str(error)},
        ) from error
    except AccountDeletionError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "account_deletion_blocked", "message": str(error)},
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "account_deletion_failed",
                "message": "Account deletion could not be completed safely",
            },
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/password-reset/request",
    response_model=PasswordResetAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> PasswordResetAccepted:
    delivery = request.app.state.password_reset_delivery
    expose_token = request.app.state.settings.password_reset_expose_token
    if not expose_token and not delivery.enabled:
        return PasswordResetAccepted()
    token = request.app.state.identity.request_password_reset(
        payload.email,
        ttl=timedelta(minutes=request.app.state.settings.password_reset_ttl_minutes),
    )
    if token is not None and delivery.enabled:
        background_tasks.add_task(_deliver_password_reset, delivery, payload.email, token)
    return PasswordResetAccepted(
        reset_token=(token if expose_token else None)
    )


@router.post(
    "/password-reset/complete",
    status_code=status.HTTP_204_NO_CONTENT,
)
def complete_password_reset(
    payload: PasswordResetComplete,
    request: Request,
) -> Response:
    try:
        request.app.state.identity.reset_password(
            payload.token,
            payload.password.get_secret_value(),
        )
    except InvalidResetTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_reset_token", "message": str(error)},
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
