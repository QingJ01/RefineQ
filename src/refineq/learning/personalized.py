"""AI-assisted targeted plans grounded in analyzed materials and learner availability."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Literal

from openai import OpenAIError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from refineq.agent.settings import ModelNotConfiguredError, ModelSettingsRepository
from refineq.agent.structured import StructuredModelResponseError, StructuredModelTransport
from refineq.learning.evidence import stable_id
from refineq.learning.models import BKTState, DifficultyState, StudyPlan, StudySession
from refineq.materials.models import MaterialAnalysis
from refineq.storage.learning import LearningRepository
from refineq.storage.material_analyses import MaterialAnalysisRepository


class TargetedPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: str
    focus_topics: list[str] = Field(min_length=1, max_length=30)
    exam_at: datetime
    daily_minutes: int = Field(ge=10, le=480)
    study_weekdays: list[int] = Field(min_length=1, max_length=7)
    preferred_hour: int = Field(ge=0, le=23)
    timezone_offset_minutes: int = Field(default=0, ge=-720, le=840)
    routine_notes: str = Field(default="", max_length=1_000)

    @field_validator("exam_at", mode="after")
    @classmethod
    def require_aware_exam_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("exam_at must be timezone-aware")
        return value

    @field_validator("study_weekdays", mode="after")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("study_weekdays must contain values from 0 to 6")
        return list(dict.fromkeys(value))


class PlannedSessionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    topic: str
    planned_at: datetime
    minutes: int = Field(ge=5, le=480)
    activity: Literal["learn", "practice", "apply", "review"]

    @field_validator("planned_at", mode="after")
    @classmethod
    def require_aware_planned_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("planned_at must be timezone-aware")
        return value


class TargetedPlanOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sessions: list[PlannedSessionOutput] = Field(min_length=1, max_length=365)


class TargetedPlanService:
    def __init__(
        self,
        learning: LearningRepository,
        analyses: MaterialAnalysisRepository,
        settings: ModelSettingsRepository,
        transport: StructuredModelTransport,
    ) -> None:
        self.learning, self.analyses = learning, analyses
        self.settings, self.transport = settings, transport

    @staticmethod
    def _fallback(payload: TargetedPlanRequest, start: datetime) -> list[PlannedSessionOutput]:
        sessions, cursor, index = [], start, 0
        while cursor < payload.exam_at and len(sessions) < 365:
            local = cursor.replace(hour=payload.preferred_hour, minute=0, second=0, microsecond=0)
            if local.weekday() in set(payload.study_weekdays) and local > start:
                sessions.append(
                    PlannedSessionOutput(
                        topic=payload.focus_topics[index % len(payload.focus_topics)],
                        planned_at=local,
                        minutes=payload.daily_minutes,
                        activity=("learn", "practice", "apply", "review")[index % 4],
                    )
                )
                index += 1
            cursor += timedelta(days=1)
        return sessions

    def generate(self, owner_id: str, workspace_id: str, payload: TargetedPlanRequest) -> StudyPlan:
        user_timezone = timezone(timedelta(minutes=payload.timezone_offset_minutes))
        start = datetime.now(user_timezone)
        local_exam_at = payload.exam_at.astimezone(user_timezone)
        analysis: MaterialAnalysis = self.analyses.get(owner_id, workspace_id, payload.material_id)
        learning_record = self.learning.get_or_create(owner_id, workspace_id)
        current_plan_data = learning_record.data.get("progress", {}).get("plan")
        current_plan = StudyPlan.model_validate(current_plan_data) if current_plan_data else None
        localized_payload = payload.model_copy(update={"exam_at": local_exam_at})
        fallback = self._fallback(localized_payload, start)
        if not fallback:
            raise ValueError("availability leaves no study session before the exam")
        try:
            output = self.transport.complete(
                settings=self.settings.load(owner_id),
                response_model=TargetedPlanOutput,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Create a personalized study schedule as strict JSON. Use only "
                            "supplied topics, stay before the exam, respect weekdays and daily "
                            "minutes, schedule every session at the exact preferred hour, and mix "
                            "learn/practice/apply/review. Return JSON shaped like "
                            '{"sessions":[{"topic":"Topic","planned_at":"ISO-8601",'
                            '"minutes":45,"activity":"learn"}]}.'
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Material summary: {analysis.summary}\n"
                            f"Available topics: {analysis.topics}\n"
                            f"Priority topics: {payload.focus_topics}\n"
                            f"Exam: {local_exam_at.isoformat()}\n"
                            f"Weekdays (Mon=0): {payload.study_weekdays}\nPreferred hour: "
                            f"{payload.preferred_hour}:00 in UTC"
                            f"{payload.timezone_offset_minutes / 60:+g}\n"
                            f"Daily minutes: {payload.daily_minutes}\n"
                            f"Routine: {payload.routine_notes}"
                        ),
                    },
                ],
            )
            allowed = set(payload.focus_topics)
            sessions = [
                item
                for item in output.sessions
                if item.topic in allowed
                and start < item.planned_at.astimezone(user_timezone) < local_exam_at
                and item.planned_at.astimezone(user_timezone).weekday()
                in set(payload.study_weekdays)
                and item.planned_at.astimezone(user_timezone).hour == payload.preferred_hour
                and item.planned_at.astimezone(user_timezone).minute == 0
            ] or fallback
        except (ModelNotConfiguredError, StructuredModelResponseError, OpenAIError, ValueError):
            sessions = fallback

        topic_names = list(dict.fromkeys(item.topic for item in sessions))
        topic_ids = {name: stable_id("topic", workspace_id, name) for name in topic_names}
        plan_id = stable_id(
            "targeted-plan",
            workspace_id,
            payload.material_id,
            payload.exam_at.isoformat(),
            *topic_names,
        )
        plan = StudyPlan(
            id=plan_id,
            goal=f"针对性学习：{', '.join(topic_names)}",
            exam_at=payload.exam_at,
            daily_minutes=payload.daily_minutes,
            sessions=[
                StudySession(
                    id=stable_id("session", plan_id, str(index), item.planned_at.isoformat()),
                    topic_id=topic_ids[item.topic],
                    planned_at=item.planned_at,
                    minutes=item.minutes,
                    activity=item.activity,
                )
                for index, item in enumerate(sessions)
            ],
        )

        merged_plan = plan

        def apply(data: dict) -> dict:
            nonlocal merged_plan
            progress = data["progress"]
            for name, topic_id in topic_ids.items():
                progress["topics"].setdefault(
                    topic_id, {"id": topic_id, "name": name, "knowledge_type": "concept"}
                )
                progress["bkt_states"].setdefault(topic_id, BKTState().model_dump(mode="json"))
                progress["difficulty_states"].setdefault(
                    topic_id, DifficultyState().model_dump(mode="json")
                )
            progress.setdefault("topic_order", list(progress["topics"]))
            for topic_id in topic_ids.values():
                if topic_id not in progress["topic_order"]:
                    progress["topic_order"].append(topic_id)
            existing_data = progress.get("plan")
            existing = StudyPlan.model_validate(existing_data) if existing_data else current_plan
            if existing:
                existing_ids = {session.id for session in existing.sessions}
                additions = [
                    session
                    for session in plan.sessions
                    if session.id not in existing_ids
                ]
                if not additions:
                    merged_plan = existing
                    progress["goal"] = merged_plan.goal
                    progress["exam_at"] = merged_plan.exam_at.astimezone(UTC).isoformat()
                    progress["daily_minutes"] = merged_plan.daily_minutes
                    progress["plan"] = merged_plan.model_dump(mode="json")
                    return data
                scheduled = list(existing.sessions)
                for addition in sorted(additions, key=lambda session: session.planned_at):
                    planned_at = addition.planned_at
                    while True:
                        conflicts = [
                            session
                            for session in scheduled
                            if planned_at < session.planned_at + timedelta(minutes=session.minutes)
                            and session.planned_at
                            < planned_at + timedelta(minutes=addition.minutes)
                        ]
                        if not conflicts:
                            break
                        planned_at = max(
                            session.planned_at + timedelta(minutes=session.minutes)
                            for session in conflicts
                        )
                    scheduled.append(addition.model_copy(update={"planned_at": planned_at}))
                combined_sessions = sorted(scheduled, key=lambda session: session.planned_at)
                combined_goal = f"{existing.goal}；新增资料：{', '.join(topic_names)}"[:500]
                merged_plan = StudyPlan(
                    id=stable_id("merged-plan", existing.id, plan.id),
                    goal=combined_goal,
                    exam_at=max(existing.exam_at, plan.exam_at),
                    daily_minutes=plan.daily_minutes,
                    sessions=combined_sessions,
                )
            progress["goal"] = merged_plan.goal
            progress["exam_at"] = merged_plan.exam_at.astimezone(UTC).isoformat()
            progress["daily_minutes"] = payload.daily_minutes
            progress["plan"] = merged_plan.model_dump(mode="json")
            return data

        with self.learning.plan_transaction(owner_id, workspace_id):
            self.learning.mutate(owner_id, workspace_id, apply)
        return merged_plan
