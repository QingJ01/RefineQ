"""Owner-derived project endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from refineq.api.dependencies import CurrentUser

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)


class ProjectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    created_at: datetime


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreateRequest,
    request: Request,
    user: CurrentUser,
) -> ProjectResponse:
    if (
        request.app.state.projects.count(user.id)
        >= request.app.state.settings.max_projects_per_user
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "project_quota", "message": "Project quota reached"},
        )
    project_id = uuid4().hex
    record = request.app.state.projects.create(user.id, project_id, name=payload.name)
    return ProjectResponse.model_validate(record.data)
