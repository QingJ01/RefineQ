"""Local registration, login, and current-user endpoints."""

from __future__ import annotations

import json
import shutil
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response, status

from refineq.api.dependencies import CurrentUser
from refineq.identity.models import (
    AccountDeleteRequest,
    AccountExportResponse,
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

    identity = request.app.state.identity
    object_storage = request.app.state.object_storage
    try:
        identity.preflight_account_deletion(user.id, current_password=current_password)
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

    staging_directory: Path | None = None
    staged_objects: list[tuple[dict[str, str], Path]] = []
    attempted_removals: list[tuple[dict[str, str], Path]] = []
    deletion_error: Exception | None = None
    rollback_failed = False
    try:
        entries = identity.account_storage_objects(user.id)
        if entries:
            recovery_root = (
                request.app.state.settings.data_root
                / "recovery"
                / "account-deletions"
            )
            recovery_root.mkdir(parents=True, exist_ok=True)
            staging_directory = recovery_root / uuid4().hex
            staging_directory.mkdir()
            for index, entry in enumerate(entries):
                staged_path = staging_directory / f"{index:06d}.bin"
                staged_path.write_bytes(object_storage.get(entry["key"]))
                staged_objects.append((entry, staged_path))
            (staging_directory / "manifest.json").write_text(
                json.dumps(entries, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        for entry, staged_path in staged_objects:
            attempted_removals.append((entry, staged_path))
            object_storage.delete(entry["key"])
        identity.delete_account(user.id, current_password=current_password)
    except Exception as error:
        deletion_error = error
        for entry, staged_path in attempted_removals:
            try:
                object_storage.put(
                    owner_id=user.id,
                    workspace_id=entry["workspace_id"],
                    material_id=entry["material_id"],
                    filename=entry["filename"],
                    payload=staged_path.read_bytes(),
                )
            except Exception:
                rollback_failed = True
        if staging_directory is not None and not rollback_failed:
            shutil.rmtree(staging_directory, ignore_errors=True)
    else:
        if staging_directory is not None:
            shutil.rmtree(staging_directory, ignore_errors=True)

    if deletion_error is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if not rollback_failed and isinstance(deletion_error, InvalidCredentialsError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_credentials", "message": str(deletion_error)},
        ) from deletion_error
    if not rollback_failed and isinstance(deletion_error, AccountDeletionError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "account_deletion_blocked", "message": str(deletion_error)},
        ) from deletion_error
    try:
        raise deletion_error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "account_deletion_failed",
                "message": "Account deletion could not be completed safely",
            },
        ) from error


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
