"""AI-assisted targeted plans grounded in analyzed materials and learner availability."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from openai import OpenAIError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from refineq.agent.settings import ModelNotConfiguredError, ModelSettingsRepository
from refineq.agent.structured import StructuredModelResponseError, StructuredModelTransport
from refineq.knowledge.index import KnowledgeIndex
from refineq.learning.evidence import stable_id
from refineq.learning.models import BKTState, DifficultyState, StudyPlan, StudySession
from refineq.learning.trusted_topics import material_answer_key_subject
from refineq.materials.models import MaterialAnalysis
from refineq.operations.recovery import RecoveryLease
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


class MaterialMutationBusyError(RuntimeError):
    pass


class TargetedPlanService:
    def __init__(
        self,
        learning: LearningRepository,
        analyses: MaterialAnalysisRepository,
        knowledge: KnowledgeIndex,
        settings: ModelSettingsRepository,
        transport: StructuredModelTransport,
        material_mutation_lease_path: Path | None = None,
    ) -> None:
        self.learning, self.analyses, self.knowledge = learning, analyses, knowledge
        self.settings, self.transport = settings, transport
        self.material_mutation_lease_path = material_mutation_lease_path

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
        self.knowledge.get_material(
            owner_id=owner_id,
            project_id=workspace_id,
            material_id=payload.material_id,
        )
        analysis: MaterialAnalysis = self.analyses.get(owner_id, workspace_id, payload.material_id)
        supported_topics = set(analysis.topics)
        unsupported = [topic for topic in payload.focus_topics if topic not in supported_topics]
        if unsupported:
            raise ValueError(
                "focus_topics must be supported by the material analysis: " + ", ".join(unsupported)
            )
        learning_record = self.learning.get_or_create(owner_id, workspace_id)
        request_key = stable_id(
            "targeted-plan-request",
            workspace_id,
            payload.material_id,
            payload.exam_at.isoformat(),
            str(payload.daily_minutes),
            ",".join(str(day) for day in payload.study_weekdays),
            str(payload.preferred_hour),
            str(payload.timezone_offset_minutes),
            payload.routine_notes,
            *payload.focus_topics,
        )
        current_progress = learning_record.data["progress"]
        current_plan_raw = current_progress.get("plan")
        request_plans = current_progress.get("targeted_plan_requests", {})
        if (
            isinstance(request_plans, dict)
            and isinstance(current_plan_raw, dict)
            and request_plans.get(request_key) == current_plan_raw.get("id")
        ):
            return StudyPlan.model_validate(current_plan_raw)
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
            sessions: list[PlannedSessionOutput] = []
            daily_minutes: dict[object, int] = {}
            for item in sorted(output.sessions, key=lambda candidate: candidate.planned_at):
                local_at = item.planned_at.astimezone(user_timezone)
                used = daily_minutes.get(local_at.date(), 0)
                overlaps = any(
                    item.planned_at < existing.planned_at + timedelta(minutes=existing.minutes)
                    and existing.planned_at < item.planned_at + timedelta(minutes=item.minutes)
                    for existing in sessions
                )
                if not (
                    item.topic in allowed
                    and start < local_at < local_exam_at
                    and local_at.weekday() in set(payload.study_weekdays)
                    and local_at.hour == payload.preferred_hour
                    and local_at.minute == 0
                    and item.minutes <= payload.daily_minutes
                    and used + item.minutes <= payload.daily_minutes
                    and not overlaps
                ):
                    continue
                sessions.append(item)
                daily_minutes[local_at.date()] = used + item.minutes
            # A structurally valid fragment is still an incomplete plan. Keep
            # the deterministic calendar when the model covers fewer study
            # opportunities than the availability contract produced.
            sessions = sessions if len(sessions) >= len(fallback) else fallback
        except (ModelNotConfiguredError, StructuredModelResponseError, OpenAIError, ValueError):
            sessions = fallback

        topic_names = list(dict.fromkeys(item.topic for item in sessions))
        topic_ids = {name: stable_id("topic", workspace_id, name) for name in topic_names}
        plan_id = stable_id(
            "targeted-plan",
            workspace_id,
            payload.material_id,
            payload.exam_at.isoformat(),
            str(payload.daily_minutes),
            ",".join(str(day) for day in payload.study_weekdays),
            str(payload.preferred_hour),
            str(payload.timezone_offset_minutes),
            payload.routine_notes,
            *(
                f"{item.topic}|{item.planned_at.isoformat()}|{item.minutes}|{item.activity}"
                for item in sessions
            ),
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

        applied_plan: list[StudyPlan] = []

        def apply(data: dict) -> dict:
            progress = data["progress"]
            request_plans = progress.setdefault("targeted_plan_requests", {})
            current_plan_raw = progress.get("plan")
            if (
                isinstance(request_plans, dict)
                and isinstance(current_plan_raw, dict)
                and request_plans.get(request_key) == current_plan_raw.get("id")
            ):
                applied_plan.append(StudyPlan.model_validate(current_plan_raw))
                return data
            for name, topic_id in topic_ids.items():
                topic = progress["topics"].setdefault(
                    topic_id,
                    {"id": topic_id, "name": name, "knowledge_type": "concept"},
                )
                answer_key_subject = material_answer_key_subject(name)
                if answer_key_subject is not None:
                    topic.setdefault("answer_key_subject", answer_key_subject)
                progress["bkt_states"].setdefault(topic_id, BKTState().model_dump(mode="json"))
                progress["difficulty_states"].setdefault(
                    topic_id, DifficultyState().model_dump(mode="json")
                )
            progress.setdefault("topic_order", list(progress["topics"]))
            for topic_id in topic_ids.values():
                if topic_id not in progress["topic_order"]:
                    progress["topic_order"].append(topic_id)
            protected_sessions: list[StudySession] = []
            pending_question = progress.get("pending_question") or {}
            pending_session_id = pending_question.get("plan_session_id") or pending_question.get(
                "review_session_id"
            )
            if isinstance(current_plan_raw, dict):
                current_plan = StudyPlan.model_validate(current_plan_raw)
                pending_session = next(
                    (
                        session
                        for session in current_plan.sessions
                        if session.id == pending_session_id
                    ),
                    None,
                )
                if pending_session is not None:
                    local_pending_at = pending_session.planned_at.astimezone(user_timezone)
                    pending_is_compatible = (
                        pending_session.minutes <= payload.daily_minutes
                        and local_pending_at < local_exam_at
                        and local_pending_at.weekday() in set(payload.study_weekdays)
                        and local_pending_at.hour == payload.preferred_hour
                        and local_pending_at.minute == 0
                    )
                    if not pending_is_compatible:
                        pending_question["plan_session_id"] = None
                        pending_question["review_session_id"] = None
                        pending_session_id = None
                protected_sessions = [
                    session
                    for session in current_plan.sessions
                    if session.status == "completed" or session.id == pending_session_id
                ]
            protected_ids = {session.id for session in protected_sessions}
            merged_sessions = protected_sessions + [
                session
                for session in plan.sessions
                if session.id not in protected_ids
                and not any(
                    session.planned_at < protected.planned_at + timedelta(minutes=protected.minutes)
                    and protected.planned_at
                    < session.planned_at + timedelta(minutes=session.minutes)
                    for protected in protected_sessions
                )
            ]
            final_plan = plan.model_copy(
                update={
                    "id": stable_id(
                        "targeted-plan-state",
                        plan.id,
                        *(f"{session.id}|{session.status}" for session in protected_sessions),
                    ),
                    "sessions": merged_sessions,
                }
            )
            progress["goal"] = final_plan.goal
            progress["exam_at"] = final_plan.exam_at.astimezone(UTC).isoformat()
            progress["daily_minutes"] = payload.daily_minutes
            progress["plan"] = final_plan.model_dump(mode="json")
            if not isinstance(request_plans, dict):
                request_plans = {}
                progress["targeted_plan_requests"] = request_plans
            request_plans[request_key] = final_plan.id
            if len(request_plans) > 50:
                for stale_key in list(request_plans)[:-50]:
                    request_plans.pop(stale_key, None)
            applied_plan.append(final_plan)
            return data

        with self.learning.plan_transaction(owner_id, workspace_id):
            lease = (
                RecoveryLease.acquire_wait(self.material_mutation_lease_path)
                if self.material_mutation_lease_path is not None
                else None
            )
            if self.material_mutation_lease_path is not None and lease is None:
                raise MaterialMutationBusyError("Another material mutation is already active")
            try:
                self.knowledge.get_material(
                    owner_id=owner_id,
                    project_id=workspace_id,
                    material_id=payload.material_id,
                )
                latest_analysis = self.analyses.get(
                    owner_id,
                    workspace_id,
                    payload.material_id,
                )
                unsupported_latest = [
                    topic
                    for topic in payload.focus_topics
                    if topic not in set(latest_analysis.topics)
                ]
                if unsupported_latest:
                    raise ValueError(
                        "focus_topics are no longer supported by the material analysis: "
                        + ", ".join(unsupported_latest)
                    )
                self.learning.mutate(owner_id, workspace_id, apply)
            finally:
                if lease is not None:
                    lease.release()
        return applied_plan[0]
