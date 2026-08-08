"""Application service for resolving and restoring personal learning spaces."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from refineq.integrations.object_storage import ConfiguredObjectStorage
from refineq.knowledge.index import KnowledgeIndex, MaterialRecord
from refineq.learning.models import LearningEvidence, StudyPlan
from refineq.learning.planning import build_study_plan
from refineq.learning.service import (
    AnswerResponse,
    LearningService,
    ProgressResponse,
    QuestionResponse,
    SavedQuestionResponse,
    SeedRequest,
    TopicSeed,
)
from refineq.storage.json_store import RecordNotFoundError
from refineq.storage.learning import LearningRepository
from refineq.storage.sessions import SessionRepository
from refineq.storage.workspaces import WorkspaceRepository
from refineq.workspaces.constraints import infer_intent_constraints
from refineq.workspaces.intelligence import WorkspaceRoutingIntelligence
from refineq.workspaces.models import LearningWorkspace
from refineq.workspaces.routing import route_workspace

DEFAULT_CAPABILITY_HORIZON_DAYS = 7


class WorkspaceServiceError(RuntimeError):
    code = "workspace_error"


class WorkspaceNotFoundError(WorkspaceServiceError):
    code = "workspace_not_found"


class WorkspaceConstraintError(WorkspaceServiceError):
    code = "invalid_learning_constraints"


class WorkspaceQuotaError(WorkspaceServiceError):
    code = "workspace_quota"


class WorkspaceResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = Field(min_length=1, max_length=2_000)
    exam_at: datetime | None = None
    daily_minutes: int | None = Field(default=None, ge=5, le=480)

    @field_validator("exam_at", mode="after")
    @classmethod
    def normalize_exam_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("exam_at must be timezone-aware")
        return value.astimezone(UTC)


class WorkspaceRouteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    workspace: LearningWorkspace


class WorkspaceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = Field(default=None, min_length=1, max_length=500)
    archived: bool | None = None


class WorkspaceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace: LearningWorkspace
    progress: ProgressResponse
    plan: StudyPlan | None
    evidence: list[LearningEvidence]
    materials: list[MaterialRecord]
    saved_questions: list[SavedQuestionResponse] = Field(default_factory=list)
    active_question: QuestionResponse | None = None
    last_answer: AnswerResponse | None = None


def _topic_id(name: str) -> str:
    return f"topic_{sha256(name.casefold().encode()).hexdigest()[:16]}"


class WorkspaceService:
    def __init__(
        self,
        *,
        workspaces: WorkspaceRepository,
        learning: LearningRepository,
        learning_service: LearningService,
        knowledge: KnowledgeIndex,
        object_storage: ConfiguredObjectStorage,
        sessions: SessionRepository,
        routing: WorkspaceRoutingIntelligence | None = None,
        max_workspaces: int = 100,
    ) -> None:
        self._workspaces = workspaces
        self._learning = learning
        self._learning_service = learning_service
        self._knowledge = knowledge
        self._object_storage = object_storage
        self._sessions = sessions
        self._routing = routing
        self._max_workspaces = max_workspaces

    def resolve(
        self,
        owner_id: str,
        payload: WorkspaceResolveRequest,
        *,
        now: datetime | None = None,
    ) -> WorkspaceRouteResponse:
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        with self._workspaces.quota_transaction(owner_id):
            return self._resolve_locked(owner_id, payload, observed_at=observed_at)

    def _resolve_locked(
        self,
        owner_id: str,
        payload: WorkspaceResolveRequest,
        *,
        observed_at: datetime,
    ) -> WorkspaceRouteResponse:
        workspaces = self._workspaces.list(owner_id)
        decision = (
            self._routing.route(payload.intent, owner_id, workspaces)
            if self._routing is not None
            else route_workspace(payload.intent, workspaces)
        )
        if decision.workspace_id is not None:
            workspace = self._workspaces.touch(
                owner_id,
                decision.workspace_id,
                now=observed_at,
            )
        else:
            if len(workspaces) >= self._max_workspaces:
                raise WorkspaceQuotaError("Learning workspace quota reached")
            workspace_id = uuid4().hex
            inferred = infer_intent_constraints(payload.intent, now=observed_at)
            exam_at = (
                payload.exam_at
                or inferred.exam_at
                or observed_at + timedelta(days=DEFAULT_CAPABILITY_HORIZON_DAYS)
            )
            daily_minutes = payload.daily_minutes or inferred.daily_minutes or 45
            topic_seeds = [TopicSeed(id=_topic_id(name), name=name) for name in decision.topics]
            try:
                build_study_plan(
                    goal=payload.intent.strip(),
                    topic_ids=[topic.id for topic in topic_seeds],
                    exam_at=exam_at,
                    daily_minutes=daily_minutes,
                    start_at=observed_at,
                )
            except ValueError as error:
                raise WorkspaceConstraintError(str(error)) from error

            try:
                workspace = self._workspaces.create(
                    owner_id,
                    workspace_id,
                    title=decision.title,
                    subject=decision.subject,
                    goal=payload.intent.strip(),
                    topics=decision.topics,
                    keywords=decision.keywords,
                    routing_summary=decision.reason,
                    now=observed_at,
                )
                self._learning_service.seed(
                    owner_id,
                    workspace.id,
                    SeedRequest(
                        goal=workspace.goal,
                        exam_at=exam_at,
                        daily_minutes=daily_minutes,
                        topics=topic_seeds,
                    ),
                )
                self._learning_service.create_plan(owner_id, workspace.id, start_at=observed_at)
            except Exception:
                self._learning.delete(owner_id, workspace_id)
                self._workspaces.delete(owner_id, workspace_id)
                raise
        return WorkspaceRouteResponse(
            action=decision.action,
            confidence=decision.confidence,
            reason=decision.reason,
            workspace=workspace,
        )

    def list(
        self,
        owner_id: str,
        *,
        include_archived: bool = False,
    ) -> list[LearningWorkspace]:
        return self._workspaces.list(owner_id, include_archived=include_archived)

    def update(
        self,
        owner_id: str,
        workspace_id: str,
        payload: WorkspaceUpdateRequest,
    ) -> LearningWorkspace:
        try:
            self._workspaces.get(owner_id, workspace_id)
            return self._workspaces.update(
                owner_id,
                workspace_id,
                title=payload.title,
                goal=payload.goal,
                archived=payload.archived,
            )
        except RecordNotFoundError as error:
            raise WorkspaceNotFoundError("Learning workspace not found") from error

    def delete(self, owner_id: str, workspace_id: str) -> None:
        try:
            self._workspaces.get(owner_id, workspace_id)
        except RecordNotFoundError as error:
            raise WorkspaceNotFoundError("Learning workspace not found") from error
        for material in self._knowledge.list_materials(
            owner_id=owner_id,
            project_id=workspace_id,
        ):
            storage_key = self._knowledge.get_material_storage_key(
                owner_id=owner_id,
                project_id=workspace_id,
                material_id=material.id,
            )
            self._object_storage.delete(storage_key)
            self._knowledge.delete_material(
                owner_id=owner_id,
                project_id=workspace_id,
                material_id=material.id,
            )
        self._learning.delete(owner_id, workspace_id)
        self._sessions.delete_for_workspace(owner_id, workspace_id)
        self._workspaces.delete(owner_id, workspace_id)

    def snapshot(self, owner_id: str, workspace_id: str) -> WorkspaceSnapshot:
        try:
            workspace = self._workspaces.get(owner_id, workspace_id)
        except RecordNotFoundError as error:
            raise WorkspaceNotFoundError("Learning workspace not found") from error
        progress = self._learning_service.progress(owner_id, workspace_id)
        learning_record = self._learning.get(owner_id, workspace_id)
        raw_plan = learning_record.data["progress"].get("plan")
        plan = StudyPlan.model_validate(raw_plan) if raw_plan else None
        raw_progress = learning_record.data["progress"]
        pending = raw_progress.get("pending_question")
        attempts = learning_record.data.get("attempts", {})
        raw_answer = next(reversed(attempts.values()), None) if attempts else None
        active_raw = pending
        if active_raw is None and raw_answer is not None:
            active_raw = raw_progress.get("question_history", {}).get(raw_answer.get("question_id"))
        active_question = (
            self._learning_service._public_question(
                active_raw,
                saved_at=raw_progress.get("saved_questions", {}).get(active_raw["id"]),
            )
            if active_raw is not None
            else None
        )
        return WorkspaceSnapshot(
            workspace=workspace,
            progress=progress,
            plan=plan,
            evidence=self._learning_service.evidence(owner_id, workspace_id),
            materials=self._knowledge.list_materials(
                owner_id=owner_id,
                project_id=workspace_id,
            ),
            saved_questions=self._learning_service.saved_questions(owner_id, workspace_id),
            active_question=active_question,
            last_answer=(
                AnswerResponse.model_validate({**raw_answer, "replayed": False})
                if pending is None and raw_answer is not None
                else None
            ),
        )
