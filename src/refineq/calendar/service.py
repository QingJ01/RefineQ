"""Build bounded user-level calendar projections from workspace-owned plans."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from refineq.calendar.models import CalendarResponse, CalendarTask
from refineq.learning.models import StudyPlan
from refineq.storage.json_store import RecordNotFoundError
from refineq.storage.learning import LearningRepository
from refineq.storage.workspaces import WorkspaceRepository

MAX_CALENDAR_RANGE = timedelta(days=370)


class CalendarRangeError(ValueError):
    code = "invalid_calendar_range"


def _normalized_range(starts_at: datetime, ends_at: datetime) -> tuple[datetime, datetime]:
    if (
        starts_at.tzinfo is None
        or starts_at.utcoffset() is None
        or ends_at.tzinfo is None
        or ends_at.utcoffset() is None
    ):
        raise CalendarRangeError("Calendar range must use timezone-aware timestamps")
    normalized_start = starts_at.astimezone(UTC)
    normalized_end = ends_at.astimezone(UTC)
    if normalized_end <= normalized_start:
        raise CalendarRangeError("Calendar range end must be after its start")
    if normalized_end - normalized_start > MAX_CALENDAR_RANGE:
        raise CalendarRangeError("Calendar range cannot exceed 370 days")
    return normalized_start, normalized_end


class CalendarService:
    def __init__(
        self,
        *,
        workspaces: WorkspaceRepository,
        learning: LearningRepository,
    ) -> None:
        self._workspaces = workspaces
        self._learning = learning

    def list_tasks(
        self,
        owner_id: str,
        *,
        starts_at: datetime,
        ends_at: datetime,
        include_archived: bool = False,
    ) -> CalendarResponse:
        range_start, range_end = _normalized_range(starts_at, ends_at)
        tasks: list[CalendarTask] = []
        for workspace in self._workspaces.list(
            owner_id,
            include_archived=include_archived,
        ):
            try:
                record = self._learning.get(owner_id, workspace.id)
            except RecordNotFoundError:
                continue
            progress = record.data.get("progress", {})
            raw_plan = progress.get("plan")
            if raw_plan is None:
                continue
            plan = StudyPlan.model_validate(raw_plan)
            topics = progress.get("topics", {})
            for session in plan.sessions:
                if not range_start <= session.planned_at < range_end:
                    continue
                tasks.append(
                    CalendarTask(
                        id=session.id,
                        workspace_id=workspace.id,
                        workspace_title=workspace.title,
                        workspace_archived=workspace.archived,
                        topic_id=session.topic_id,
                        topic_label=str(topics.get(session.topic_id) or session.topic_id),
                        planned_at=session.planned_at,
                        minutes=session.minutes,
                        activity=session.activity,
                        status=session.status,
                    )
                )
        tasks.sort(key=lambda task: (task.planned_at, task.workspace_title, task.id))
        return CalendarResponse(
            starts_at=range_start,
            ends_at=range_end,
            tasks=tasks,
        )

