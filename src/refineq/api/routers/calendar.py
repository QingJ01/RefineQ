"""Authenticated user-level calendar projection."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status

from refineq.api.dependencies import CurrentUser
from refineq.calendar.models import CalendarResponse
from refineq.calendar.service import CalendarRangeError

router = APIRouter(tags=["calendar"])


@router.get("/calendar", response_model=CalendarResponse)
def list_calendar(
    request: Request,
    user: CurrentUser,
    starts_at: datetime,
    ends_at: datetime,
    include_archived: bool = False,
) -> CalendarResponse:
    try:
        return request.app.state.calendar_service.list_tasks(
            user.id,
            starts_at=starts_at,
            ends_at=ends_at,
            include_archived=include_archived,
        )
    except CalendarRangeError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": error.code, "message": str(error)},
        ) from error
