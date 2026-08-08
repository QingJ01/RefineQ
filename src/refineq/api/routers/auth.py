"""Local registration, login, and current-user endpoints."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status

from refineq.api.dependencies import CurrentUser
from refineq.identity.models import (
    AuthResponse,
    LoginRequest,
    PasswordResetAccepted,
    PasswordResetComplete,
    PasswordResetRequest,
    RegisterRequest,
    User,
)
from refineq.identity.service import (
    AccountExistsError,
    InvalidCredentialsError,
    InvalidResetTokenError,
)

router = APIRouter(prefix="/auth", tags=["identity"])


def _auth_response(request: Request, user: User) -> AuthResponse:
    return AuthResponse(
        access_token=request.app.state.identity.issue_token(user),
        user=user,
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
        user = request.app.state.identity.authenticate(
            email=payload.email,
            password=payload.password.get_secret_value(),
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
    return _auth_response(request, user)


@router.get("/me", response_model=User)
def me(user: CurrentUser) -> User:
    return user


@router.post(
    "/password-reset/request",
    response_model=PasswordResetAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
) -> PasswordResetAccepted:
    token = request.app.state.identity.request_password_reset(
        payload.email,
        ttl=timedelta(minutes=request.app.state.settings.password_reset_ttl_minutes),
    )
    return PasswordResetAccepted(
        reset_token=(token if request.app.state.settings.password_reset_expose_token else None)
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
