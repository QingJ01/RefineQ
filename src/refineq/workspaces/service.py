"""Application service for resolving and restoring personal learning spaces."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from refineq.knowledge.deletion import MaterialDeletionCoordinator, PendingMaterialDeletion
from refineq.knowledge.index import KnowledgeIndex, MaterialRecord
from refineq.learning.models import LearningEvidence, StudyPlan
from refineq.learning.next_action import NextAction, select_next_action
from refineq.learning.planning import build_study_plan
from refineq.learning.service import (
    AnswerResponse,
    LearningService,
    PlanUpdateRequest,
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
from refineq.workspaces.models import LearningWorkspace, WorkspaceRoutingDecision
from refineq.workspaces.routing import route_workspace

DEFAULT_CAPABILITY_HORIZON_DAYS = 7
MAX_TOPIC_SUGGESTION_MATERIALS = 50
MAX_TOPIC_SUGGESTIONS = 12
MAX_TOPIC_SUGGESTION_SOURCES = 20


class WorkspaceServiceError(RuntimeError):
    code = "workspace_error"


class WorkspaceNotFoundError(WorkspaceServiceError):
    code = "workspace_not_found"


class WorkspaceConstraintError(WorkspaceServiceError):
    code = "invalid_learning_constraints"


class WorkspaceQuotaError(WorkspaceServiceError):
    code = "workspace_quota"


class WorkspaceConflictError(WorkspaceServiceError):
    code = "workspace_conflict"


class WorkspaceMaterialRequiredError(WorkspaceServiceError):
    code = "material_required"


class TopicSuggestionNotFoundError(WorkspaceServiceError):
    code = "topic_suggestion_not_found"


@dataclass(frozen=True, slots=True)
class DeferredWorkspaceDeletion:
    """Workspace material links awaiting finalization by a coordinating action."""

    pending_materials: PendingMaterialDeletion
    owner_id: str
    workspace_id: str
    linked_material_ids: tuple[str, ...]


class WorkspaceResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = Field(min_length=1, max_length=2_000)
    exam_at: datetime | None = None
    daily_minutes: int | None = Field(default=None, ge=5, le=480)
    timezone_offset_minutes: int = Field(default=0, ge=-840, le=840)

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


class WorkspaceResolutionPreview(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    payload: WorkspaceResolveRequest
    decision: WorkspaceRoutingDecision
    workspace_snapshot_hash: str
    observed_at: datetime


class WorkspaceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = Field(default=None, min_length=1, max_length=500)
    archived: bool | None = None


class TopicSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    name: str = Field(min_length=1, max_length=200)
    source_material_ids: list[str] = Field(min_length=1, max_length=20)


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
    topic_suggestions: list[TopicSuggestion] = Field(default_factory=list)
    next_action: NextAction


def _topic_id(name: str) -> str:
    return f"topic_{sha256(name.casefold().encode()).hexdigest()[:16]}"


def _material_topic_suggestions(
    workspace: LearningWorkspace,
    materials: list[MaterialRecord],
) -> list[TopicSuggestion]:
    """Derive bounded candidates from user-visible metadata, never material content."""

    if len(workspace.topics) >= 200:
        return []
    existing = {name.casefold() for name in workspace.topics}
    candidates: dict[str, tuple[str, list[str]]] = {}
    bounded_materials = sorted(
        materials,
        key=lambda item: (item.indexed_at, item.id),
        reverse=True,
    )[:MAX_TOPIC_SUGGESTION_MATERIALS]
    for material in bounded_materials:
        if material.status != "indexed":
            continue
        for raw_name in [material.title, *material.tags]:
            name = " ".join(raw_name.split()).strip()
            key = name.casefold()
            if not name or len(name) > 200 or key in existing:
                continue
            if key not in candidates:
                if len(candidates) >= MAX_TOPIC_SUGGESTIONS:
                    continue
                candidates[key] = (name, [])
            sources = candidates[key][1]
            if material.id not in sources and len(sources) < MAX_TOPIC_SUGGESTION_SOURCES:
                sources.append(material.id)
    return [
        TopicSuggestion(
            id=_topic_id(name),
            name=name,
            source_material_ids=sources,
        )
        for name, sources in candidates.values()
    ]


class WorkspaceService:
    def __init__(
        self,
        *,
        workspaces: WorkspaceRepository,
        learning: LearningRepository,
        learning_service: LearningService,
        knowledge: KnowledgeIndex,
        material_deletions: MaterialDeletionCoordinator,
        sessions: SessionRepository,
        routing: WorkspaceRoutingIntelligence | None = None,
        max_workspaces: int = 100,
    ) -> None:
        self._workspaces = workspaces
        self._learning = learning
        self._learning_service = learning_service
        self._knowledge = knowledge
        self._material_deletions = material_deletions
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
        preview = self.preview_resolution(owner_id, payload, now=now)
        return self.commit_resolution(owner_id, preview)

    @staticmethod
    def _workspace_snapshot_hash(workspaces: list[LearningWorkspace]) -> str:
        serialized = "|".join(
            item.model_dump_json() for item in sorted(workspaces, key=lambda value: value.id)
        )
        return sha256(serialized.encode()).hexdigest()

    def preview_resolution(
        self,
        owner_id: str,
        payload: WorkspaceResolveRequest,
        *,
        now: datetime | None = None,
        use_model: bool = True,
    ) -> WorkspaceResolutionPreview:
        """Resolve against an owner snapshot without touching or creating state."""

        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        workspaces = self._workspaces.list(owner_id)
        decision = (
            self._routing.route(payload.intent, owner_id, workspaces)
            if use_model and self._routing is not None
            else route_workspace(payload.intent, workspaces)
        )
        return WorkspaceResolutionPreview(
            payload=payload,
            decision=decision,
            workspace_snapshot_hash=self._workspace_snapshot_hash(workspaces),
            observed_at=observed_at,
        )

    def commit_resolution(
        self,
        owner_id: str,
        preview: WorkspaceResolutionPreview,
    ) -> WorkspaceRouteResponse:
        """Commit a preview only while its owner-scoped workspace snapshot is current."""

        payload = preview.payload
        decision = preview.decision
        observed_at = preview.observed_at
        with self._workspaces.quota_transaction(owner_id):
            latest = self._workspaces.list(owner_id)
            if decision.workspace_id is None and len(latest) >= self._max_workspaces:
                raise WorkspaceQuotaError("Learning workspace quota reached")
            if self._workspace_snapshot_hash(latest) != preview.workspace_snapshot_hash:
                raise WorkspaceConflictError("Learning workspaces changed during routing")
            response = self._commit_resolution(
                owner_id,
                payload,
                decision,
                latest,
                observed_at=observed_at,
            )
            intent_key = sha256(payload.intent.strip().casefold().encode()).hexdigest()[:20]
            self._learning_service.try_record_journey_event(
                owner_id,
                response.workspace.id,
                name="intent_submitted",
                idempotency_key=f"{observed_at:%Y%m%d%H%M}:{intent_key}",
                occurred_at=observed_at,
            )
            if response.action == "created":
                self._learning_service.try_record_journey_event(
                    owner_id,
                    response.workspace.id,
                    name="workspace_ready",
                    idempotency_key=response.workspace.id,
                    occurred_at=observed_at,
                    ref_id=response.workspace.id,
                )
            return response

    def _commit_resolution(
        self,
        owner_id: str,
        payload: WorkspaceResolveRequest,
        decision: WorkspaceRoutingDecision,
        workspaces: list[LearningWorkspace],
        *,
        observed_at: datetime,
    ) -> WorkspaceRouteResponse:
        user_timezone = timezone(timedelta(minutes=payload.timezone_offset_minutes))
        local_observed_at = observed_at.astimezone(user_timezone)
        inferred = infer_intent_constraints(payload.intent, now=local_observed_at)
        should_generate_plan = any(
            (
                payload.exam_at is not None,
                payload.daily_minutes is not None,
                inferred.exam_at is not None,
                inferred.daily_minutes is not None,
                inferred.preferred_hour is not None,
                inferred.plan_requested,
            )
        )
        exam_at = (
            payload.exam_at
            or inferred.exam_at
            or observed_at + timedelta(days=DEFAULT_CAPABILITY_HORIZON_DAYS)
        )
        daily_minutes = payload.daily_minutes or inferred.daily_minutes or 45
        plan_start_at = observed_at
        if inferred.preferred_hour is not None:
            local_start = local_observed_at.replace(
                hour=inferred.preferred_hour,
                minute=0,
                second=0,
                microsecond=0,
            )
            if local_start <= local_observed_at:
                local_start += timedelta(days=1)
            plan_start_at = local_start.astimezone(UTC)

        if decision.workspace_id is not None:
            try:
                workspace = self._workspaces.touch(
                    owner_id,
                    decision.workspace_id,
                    now=observed_at,
                )
            except RecordNotFoundError as error:
                raise WorkspaceConflictError(
                    "Selected learning workspace no longer exists"
                ) from error
            progress = self._learning_service.progress(owner_id, workspace.id)
            if should_generate_plan and progress.plan_id is None:
                self.update_plan(
                    owner_id,
                    workspace.id,
                    PlanUpdateRequest(
                        goal=payload.intent.strip(),
                        exam_at=exam_at,
                        daily_minutes=daily_minutes,
                        topic_order=progress.topic_order,
                        regenerate=True,
                    ),
                    start_at=plan_start_at,
                )
                workspace = self._workspaces.get(owner_id, workspace.id)
        else:
            if len(workspaces) >= self._max_workspaces:
                raise WorkspaceQuotaError("Learning workspace quota reached")
            workspace_id = uuid4().hex
            topic_seeds = [TopicSeed(id=_topic_id(name), name=name) for name in decision.topics]
            try:
                build_study_plan(
                    goal=payload.intent.strip(),
                    topic_ids=[topic.id for topic in topic_seeds],
                    exam_at=exam_at,
                    daily_minutes=daily_minutes,
                    start_at=plan_start_at,
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
                if should_generate_plan:
                    self._learning_service.create_plan(
                        owner_id,
                        workspace.id,
                        start_at=plan_start_at,
                    )
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

    def topic_suggestions(
        self,
        owner_id: str,
        workspace_id: str,
    ) -> list[TopicSuggestion]:
        try:
            workspace = self._workspaces.get(owner_id, workspace_id)
        except RecordNotFoundError as error:
            raise WorkspaceNotFoundError("Learning workspace not found") from error
        materials = self._knowledge.list_materials(
            owner_id=owner_id,
            project_id=workspace_id,
        )
        return _material_topic_suggestions(workspace, materials)

    def accept_topic_suggestion(
        self,
        owner_id: str,
        workspace_id: str,
        suggestion_id: str,
        *,
        now: datetime | None = None,
    ) -> WorkspaceSnapshot:
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        try:
            with self._learning.plan_transaction(owner_id, workspace_id):
                workspace = self._workspaces.get(owner_id, workspace_id)
                if any(_topic_id(name) == suggestion_id for name in workspace.topics):
                    return self.snapshot(owner_id, workspace_id)
                suggestion = next(
                    (
                        item
                        for item in self.topic_suggestions(owner_id, workspace_id)
                        if item.id == suggestion_id
                    ),
                    None,
                )
                if suggestion is None:
                    raise TopicSuggestionNotFoundError("Topic suggestion not found")
                workspace_snapshot = self._workspaces.snapshot(owner_id, workspace_id)
                learning_snapshot = self._learning.get(owner_id, workspace_id)
                try:
                    self._workspaces.append_topic(owner_id, workspace_id, suggestion.name)
                    self._learning_service.add_topic(
                        owner_id,
                        workspace_id,
                        TopicSeed(id=suggestion.id, name=suggestion.name),
                        start_at=observed_at,
                    )
                except Exception:
                    try:
                        self._workspaces.restore(owner_id, workspace_id, workspace_snapshot)
                    finally:
                        self._learning.restore(owner_id, workspace_id, learning_snapshot)
                    raise
                return self.snapshot(owner_id, workspace_id)
        except RecordNotFoundError as error:
            raise WorkspaceNotFoundError("Learning workspace not found") from error

    def update_plan(
        self,
        owner_id: str,
        workspace_id: str,
        payload: PlanUpdateRequest,
        *,
        start_at: datetime | None = None,
    ) -> StudyPlan:
        plan_fields = ("goal", "exam_at", "daily_minutes", "topic_order", "plan")
        try:
            with self._learning.plan_transaction(owner_id, workspace_id):
                self._workspaces.get(owner_id, workspace_id)
                progress = self._learning.get(owner_id, workspace_id).data["progress"]
                original_plan_fields = {
                    field: deepcopy(progress[field]) for field in plan_fields if field in progress
                }
                plan = self._learning_service.update_plan(
                    owner_id,
                    workspace_id,
                    payload,
                    start_at=start_at,
                )
                try:
                    self._workspaces.update(owner_id, workspace_id, goal=payload.goal)
                except Exception:

                    def restore(data: dict) -> dict:
                        current_progress = data["progress"]
                        for field in plan_fields:
                            if field in original_plan_fields:
                                current_progress[field] = deepcopy(original_plan_fields[field])
                            else:
                                current_progress.pop(field, None)
                        return data

                    self._learning.mutate(owner_id, workspace_id, restore)
                    raise
                return plan
        except RecordNotFoundError as error:
            raise WorkspaceNotFoundError("Learning workspace not found") from error

    def delete(
        self,
        owner_id: str,
        workspace_id: str,
        *,
        precondition: Callable[[], None] | None = None,
        defer_material_finalization: bool = False,
    ) -> DeferredWorkspaceDeletion | None:
        workspace_snapshot = None
        learning_snapshot = None
        journey_event_snapshot = None
        session_snapshots = []
        linked_material_ids: list[str] = []
        pending: PendingMaterialDeletion | None = None
        try:
            with self._learning.plan_transaction(owner_id, workspace_id):
                try:
                    self._workspaces.get(owner_id, workspace_id)
                except RecordNotFoundError as error:
                    raise WorkspaceNotFoundError("Learning workspace not found") from error
                workspace_snapshot = self._workspaces.snapshot(owner_id, workspace_id)
                learning_snapshot = self._learning.get(owner_id, workspace_id)
                journey_event_snapshot = self._learning_service.snapshot_journey_events(
                    owner_id,
                    workspace_id,
                )
                session_snapshots = self._sessions.snapshot_for_workspace(
                    owner_id,
                    workspace_id,
                )
                linked_material_ids = [
                    material.id
                    for material in self._knowledge.list_materials(
                        owner_id=owner_id,
                        project_id=workspace_id,
                    )
                ]
                if defer_material_finalization:
                    pending = self._material_deletions.prepare(
                        owner_id=owner_id,
                        project_id=workspace_id,
                        material_ids=[],
                    )
                if precondition is not None:
                    precondition()
                self._learning.delete(owner_id, workspace_id)
                self._learning_service.delete_journey_events(owner_id, workspace_id)
                self._sessions.delete_for_workspace(owner_id, workspace_id)
                self._workspaces.delete(owner_id, workspace_id)

            if defer_material_finalization:
                if pending is None:
                    raise RuntimeError("Deferred workspace deletion lease was not acquired")
                return DeferredWorkspaceDeletion(
                    pending_materials=pending,
                    owner_id=owner_id,
                    workspace_id=workspace_id,
                    linked_material_ids=tuple(linked_material_ids),
                )
            if linked_material_ids:
                self._knowledge.unlink_materials(
                    owner_id=owner_id,
                    workspace_id=workspace_id,
                    material_ids=linked_material_ids,
                )
            return None
        except Exception:
            if workspace_snapshot is not None and learning_snapshot is not None:
                with self._learning.plan_transaction(owner_id, workspace_id):
                    self._workspaces.restore(
                            owner_id,
                            workspace_id,
                            workspace_snapshot,
                    )
                    self._learning.restore(
                            owner_id,
                            workspace_id,
                            learning_snapshot,
                    )
                    if journey_event_snapshot is not None:
                        self._learning_service.restore_journey_events(
                                owner_id,
                                workspace_id,
                                journey_event_snapshot,
                        )
                    self._sessions.restore_snapshots(owner_id, session_snapshots)
            if pending is not None:
                self._material_deletions.rollback(pending)
            raise

    def finalize_deferred_delete(self, deletion: DeferredWorkspaceDeletion) -> None:
        """Remove workspace links after the coordinating action commits."""

        try:
            if deletion.linked_material_ids:
                self._knowledge.unlink_materials(
                    owner_id=deletion.owner_id,
                    workspace_id=deletion.workspace_id,
                    material_ids=list(deletion.linked_material_ids),
                )
            self._material_deletions.complete(deletion.pending_materials)
        except Exception:
            self._material_deletions.rollback(deletion.pending_materials)
            raise

    def abort_deferred_delete(self, deletion: DeferredWorkspaceDeletion) -> None:
        """Keep workspace links intact when the coordinating action rolls back."""

        self._material_deletions.rollback(deletion.pending_materials)

    def require_searchable_material(self, owner_id: str, workspace_id: str) -> None:
        try:
            self._workspaces.get(owner_id, workspace_id)
        except RecordNotFoundError as error:
            raise WorkspaceNotFoundError("Learning workspace not found") from error
        if not self._knowledge.list_materials(
            owner_id=owner_id,
            project_id=workspace_id,
            status="indexed",
        ):
            raise WorkspaceMaterialRequiredError(
                "Upload a searchable material before starting a learning task"
            )

    def next_action(
        self,
        owner_id: str,
        workspace_id: str,
        *,
        now: datetime | None = None,
        timezone_offset_minutes: int = 0,
    ) -> NextAction:
        try:
            self._workspaces.get(owner_id, workspace_id)
            learning_record = self._learning.get(owner_id, workspace_id)
        except RecordNotFoundError as error:
            raise WorkspaceNotFoundError("Learning workspace not found") from error
        progress = self._learning_service.progress(owner_id, workspace_id)
        raw_plan = learning_record.data["progress"].get("plan")
        plan = StudyPlan.model_validate(raw_plan) if raw_plan else None
        materials = self._knowledge.list_materials(
            owner_id=owner_id,
            project_id=workspace_id,
        )
        return select_next_action(
            workspace_id=workspace_id,
            version=learning_record.version,
            plan=plan,
            material_statuses=[material.status for material in materials],
            mastery=progress.mastery,
            topic_names=progress.topics,
            now=(now or datetime.now(UTC)).astimezone(UTC),
            timezone_offset_minutes=timezone_offset_minutes,
        )

    def snapshot(
        self,
        owner_id: str,
        workspace_id: str,
        *,
        now: datetime | None = None,
        timezone_offset_minutes: int = 0,
    ) -> WorkspaceSnapshot:
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        try:
            workspace = self._workspaces.get(owner_id, workspace_id)
        except RecordNotFoundError as error:
            raise WorkspaceNotFoundError("Learning workspace not found") from error
        self._learning_service.try_record_journey_event(
            owner_id,
            workspace_id,
            name="workspace_opened",
            idempotency_key=f"{observed_at:%Y%m%d}",
            occurred_at=observed_at,
            ref_id=workspace_id,
        )
        self._learning_service.quarantine_ungrounded_pending(owner_id, workspace_id)
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
            active_raw = raw_progress.get("question_history", {}).get(
                raw_answer.get("question_id")
            ) or raw_answer.get("question_snapshot")
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
            topic_suggestions=self.topic_suggestions(owner_id, workspace_id),
            next_action=self.next_action(
                owner_id,
                workspace_id,
                now=observed_at,
                timezone_offset_minutes=timezone_offset_minutes,
            ),
        )
