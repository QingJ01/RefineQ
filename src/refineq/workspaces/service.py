"""Application service for resolving and restoring personal learning spaces."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from refineq.knowledge.index import KnowledgeIndex, MaterialRecord
from refineq.learning.models import LearningEvidence, StudyPlan
from refineq.learning.service import LearningService, ProgressResponse, SeedRequest, TopicSeed
from refineq.storage.json_store import RecordNotFoundError
from refineq.storage.learning import LearningRepository
from refineq.storage.workspaces import WorkspaceRepository
from refineq.workspaces.intelligence import WorkspaceRoutingIntelligence
from refineq.workspaces.models import LearningWorkspace
from refineq.workspaces.routing import route_workspace


class WorkspaceServiceError(RuntimeError):
    code = "workspace_error"


class WorkspaceNotFoundError(WorkspaceServiceError):
    code = "workspace_not_found"


class WorkspaceResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = Field(min_length=1, max_length=2_000)
    exam_at: datetime | None = None
    daily_minutes: int = Field(default=45, ge=5, le=480)

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


class WorkspaceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace: LearningWorkspace
    progress: ProgressResponse
    plan: StudyPlan | None
    evidence: list[LearningEvidence]
    materials: list[MaterialRecord]


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
        routing: WorkspaceRoutingIntelligence | None = None,
    ) -> None:
        self._workspaces = workspaces
        self._learning = learning
        self._learning_service = learning_service
        self._knowledge = knowledge
        self._routing = routing

    def resolve(
        self,
        owner_id: str,
        payload: WorkspaceResolveRequest,
        *,
        now: datetime | None = None,
    ) -> WorkspaceRouteResponse:
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
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
            workspace_id = uuid4().hex
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
            exam_at = payload.exam_at or observed_at + timedelta(days=30)
            self._learning_service.seed(
                owner_id,
                workspace.id,
                SeedRequest(
                    goal=workspace.goal,
                    exam_at=exam_at,
                    daily_minutes=payload.daily_minutes,
                    topics=[
                        TopicSeed(id=_topic_id(name), name=name)
                        for name in workspace.topics
                    ],
                ),
            )
            self._learning_service.create_plan(owner_id, workspace.id)
        return WorkspaceRouteResponse(
            action=decision.action,
            confidence=decision.confidence,
            reason=decision.reason,
            workspace=workspace,
        )

    def list(self, owner_id: str) -> list[LearningWorkspace]:
        return self._workspaces.list(owner_id)

    def snapshot(self, owner_id: str, workspace_id: str) -> WorkspaceSnapshot:
        try:
            workspace = self._workspaces.get(owner_id, workspace_id)
        except RecordNotFoundError as error:
            raise WorkspaceNotFoundError("Learning workspace not found") from error
        progress = self._learning_service.progress(owner_id, workspace_id)
        learning_record = self._learning.get(owner_id, workspace_id)
        raw_plan = learning_record.data["progress"].get("plan")
        plan = StudyPlan.model_validate(raw_plan) if raw_plan else None
        return WorkspaceSnapshot(
            workspace=workspace,
            progress=progress,
            plan=plan,
            evidence=self._learning_service.evidence(owner_id, workspace_id),
            materials=self._knowledge.list_materials(
                owner_id=owner_id,
                project_id=workspace_id,
            ),
        )
