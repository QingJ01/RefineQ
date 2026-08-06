"""Protected model-settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from refineq.agent.settings import (
    ModelEndpointNotAllowedError,
    ModelSettings,
    PublicModelSettings,
)
from refineq.api.dependencies import CurrentUser

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/model", response_model=PublicModelSettings)
def get_model_settings(request: Request, user: CurrentUser) -> PublicModelSettings:
    return request.app.state.model_settings.public(user.id)


@router.put("/model", response_model=PublicModelSettings)
def update_model_settings(
    payload: ModelSettings,
    request: Request,
    user: CurrentUser,
) -> PublicModelSettings:
    try:
        request.app.state.model_settings.save(user.id, payload)
    except ModelEndpointNotAllowedError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "model_endpoint_not_allowed", "message": str(error)},
        ) from error
    return request.app.state.model_settings.public(user.id)
