"""Protected model-settings endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from refineq.agent.settings import ModelSettings, PublicModelSettings
from refineq.api.dependencies import CurrentUser

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/model", response_model=PublicModelSettings)
def get_model_settings(request: Request, _user: CurrentUser) -> PublicModelSettings:
    return request.app.state.model_settings.public()


@router.put("/model", response_model=PublicModelSettings)
def update_model_settings(
    payload: ModelSettings,
    request: Request,
    _user: CurrentUser,
) -> PublicModelSettings:
    request.app.state.model_settings.save(payload)
    return request.app.state.model_settings.public()
