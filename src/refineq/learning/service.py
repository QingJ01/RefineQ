"""Application service for the deterministic learning journey."""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from refineq.knowledge.index import SearchResult
from refineq.learning.bkt import DEFAULT_BKT, mastery_is_stable, update_bkt
from refineq.learning.difficulty import update_difficulty
from refineq.learning.events import JourneyEvent, JourneyEventName, build_journey_event
from refineq.learning.evidence import create_evidence, stable_id
from refineq.learning.intelligence import (
    GeneratedQuestion,
    LearningIntelligenceService,
    fallback_grade,
    fallback_question,
)
from refineq.learning.models import (
    BKTState,
    DifficultyState,
    Grounding,
    KnowledgeType,
    LearningEvidence,
    LearningMode,
    StudyPlan,
    StudySession,
)
from refineq.learning.next_action import _local_date
from refineq.learning.planning import build_study_plan
from refineq.learning.session_adaptation import (
    decide_next_session_action,
    summary_reserve_minutes,
)
from refineq.storage.journey_events import JourneyEventRepository
from refineq.storage.json_store import RecordNotFoundError, StoredRecord
from refineq.storage.learning import LearningRepository
from refineq.storage.projects import ProjectRepository

MAX_QUESTION_HISTORY = 200
logger = logging.getLogger(__name__)
MAX_SAVED_QUESTIONS = 100
MAX_QUESTION_REQUESTS = 100
MAX_REVIEW_SESSIONS = 20
MAX_CREDITED_QUESTIONS = 50
PLAN_ACTIVITY_MODES = {
    "learn": LearningMode.CONCEPT,
    "practice": LearningMode.CASE,
    "apply": LearningMode.PROJECT,
    "review": LearningMode.EXAM,
}


def _recent_learning_needs(
    progress: dict[str, Any],
    topic_id: str,
    *,
    limit: int = 3,
) -> list[dict[str, list[str]]]:
    """Return bounded, same-topic feedback without inventing or merging diagnoses."""

    selected: list[dict[str, list[str]]] = []
    for raw_evidence in reversed(progress.get("evidence", [])):
        details = raw_evidence.get("details", {})
        if not isinstance(details, dict) or details.get("topic_id") != topic_id:
            continue
        gaps = [
            value.strip()[:300]
            for value in details.get("gaps", [])[:5]
            if isinstance(value, str) and value.strip()
        ]
        misconceptions = [
            value.strip()[:300]
            for value in details.get("misconceptions", [])[:5]
            if isinstance(value, str) and value.strip()
        ]
        if not gaps and not misconceptions:
            continue
        selected.append({"gaps": gaps, "misconceptions": misconceptions})
        if len(selected) == limit:
            break
    return list(reversed(selected))


def _upsert_review_session(
    raw_plan: dict[str, Any],
    candidate: StudySession,
    *,
    not_before: datetime | None = None,
) -> datetime:
    """Keep the earliest useful pending review per topic and bound dynamic history."""

    sessions = raw_plan["sessions"]
    sessions[:] = [
        item
        for item in sessions
        if not (
            item.get("activity") == "review"
            and str(item.get("id", "")).startswith("review_")
            and item.get("topic_id") == candidate.topic_id
            and item.get("status", "planned") != "completed"
        )
    ]
    planned_review = min(
        (
            (item, StudySession.model_validate(item))
            for item in sessions
            if item.get("activity") == "review"
            and not str(item.get("id", "")).startswith("review_")
            and item.get("topic_id") == candidate.topic_id
            and item.get("status", "planned") != "completed"
        ),
        key=lambda pair: (pair[1].planned_at, pair[1].id),
        default=None,
    )
    if planned_review is None:
        sessions.append(candidate.model_dump(mode="json"))
        selected_at = candidate.planned_at
    else:
        planned_item, planned_session = planned_review
        selected_at = min(planned_session.planned_at, candidate.planned_at)
        if not_before is not None:
            selected_at = max(selected_at, not_before)
        planned_item["planned_at"] = selected_at.isoformat()

    reviews = [
        item
        for item in sessions
        if item.get("activity") == "review" and str(item.get("id", "")).startswith("review_")
    ]
    excess = len(reviews) - MAX_REVIEW_SESSIONS
    if excess > 0:
        removable = sorted(
            reviews,
            key=lambda item: (
                item.get("status", "planned") != "completed",
                item["planned_at"],
                item["id"],
            ),
        )[:excess]
        remove_ids = {item["id"] for item in removable}
        sessions[:] = [item for item in sessions if item.get("id") not in remove_ids]
    sessions.sort(key=lambda item: item["planned_at"])
    return selected_at


class LearningServiceError(RuntimeError):
    code = "learning_error"


class ProjectNotFoundError(LearningServiceError):
    code = "project_not_found"


class LearningNotSeededError(LearningServiceError):
    code = "learning_not_seeded"


class LearningConflictError(LearningServiceError):
    code = "learning_conflict"


class DailyCapacityExceededError(LearningConflictError):
    code = "daily_capacity_exceeded"

    def __init__(self, message: str, *, detail: dict[str, Any]) -> None:
        super().__init__(message)
        self.detail = detail


class MaterialGroundingRequiredError(LearningConflictError):
    code = "material_insufficient"


class QuestionNotFoundError(LearningServiceError):
    code = "question_not_found"


class AttemptNotFoundError(LearningServiceError):
    code = "attempt_not_found"


class TopicSeed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    name: str = Field(min_length=1, max_length=200)
    knowledge_type: KnowledgeType = KnowledgeType.CONCEPT


class SeedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=500)
    exam_at: datetime
    daily_minutes: int = Field(ge=5, le=480)
    topics: list[TopicSeed] = Field(min_length=1, max_length=200)


class DiagnosticResultInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    topic_id: str = Field(min_length=1)
    is_correct: bool


class DiagnosticRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diagnostic_id: Literal["initial"] = "initial"
    results: list[DiagnosticResultInput] = Field(min_length=1, max_length=200)


class QuestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    topic_id: str
    prompt: str
    explanation: str | None = None
    difficulty_level: int = Field(default=2, ge=1, le=5)
    citations: list[str] = Field(default_factory=list)
    sources: list[SearchResult] = Field(default_factory=list)
    grounding: Grounding = Grounding.GENERAL
    learning_mode: LearningMode = LearningMode.CONCEPT
    mode: str = "fallback"
    saved: bool = False
    review_session_id: str | None = None
    plan_session_id: str | None = None
    state_version: int = 0
    prompt_hash: str = ""


class SavedQuestionResponse(QuestionResponse):
    saved_at: datetime | None = None


class QuestionSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    saved: bool


class QuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    topic_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$",
    )
    difficulty: int | None = Field(default=None, ge=1, le=5)
    mode: LearningMode = LearningMode.CONCEPT
    replace: bool = False
    review_session_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$",
    )
    plan_session_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$",
    )

    @model_validator(mode="after")
    def select_one_session_origin(self) -> QuestionRequest:
        if self.plan_session_id is not None and self.review_session_id is not None:
            raise ValueError("plan_session_id and review_session_id are mutually exclusive")
        return self


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    question_id: str = Field(min_length=1)
    answer: str = Field(min_length=1, max_length=10_000)
    remaining_minutes: int | None = Field(default=None, ge=0, le=480)
    summary_reserve_minutes: int | None = Field(default=None, ge=1, le=30)
    prompt_hash: str | None = Field(default=None, max_length=128)


class SessionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["continue_topic", "next_topic", "summary"]
    reason: Literal["time_low", "mastery_low", "mastery_reached", "no_next_topic"]
    topic_id: str | None = None
    estimated_minutes: int = Field(ge=1, le=60)
    remaining_minutes: int | None = Field(default=None, ge=0, le=480)
    summary_reserve_minutes: int = Field(ge=1, le=30)
    target_mastery: float = Field(ge=0.0, le=1.0)


class AnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: str
    question_id: str
    topic_id: str
    is_correct: bool
    mastery: float = Field(ge=0.0, le=1.0)
    difficulty_level: int = Field(ge=1, le=5)
    evidence_id: str
    score: int = Field(default=0, ge=0, le=100)
    feedback: str = ""
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    sources: list[SearchResult] = Field(default_factory=list)
    grounding: Grounding = Grounding.GENERAL
    grading_mode: str = "fallback"
    reason_code: str = "ok"
    mastery_updated: bool = True
    next_review_at: datetime | None = None
    answer: str = ""
    observed_at: datetime | None = None
    learner_note: str | None = None
    appealed: bool = False
    completed_review_session_id: str | None = None
    completed_plan_session_id: str | None = None
    session_decision: SessionDecision | None = None
    question_snapshot: dict[str, Any] | None = Field(default=None, exclude=True)
    replayed: bool = False


class PlanSessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = Field(default=None, pattern=r"^(planned|completed)$")
    planned_at: datetime | None = None
    minutes: int | None = Field(default=None, ge=5, le=480)
    topic_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$",
    )
    timezone_offset_minutes: int = Field(default=0, ge=-840, le=840)


class PlanSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic_name: str = Field(min_length=1, max_length=200)
    planned_at: datetime
    minutes: int = Field(ge=5, le=480)
    activity: str = Field(default="practice", pattern=r"^(learn|practice|apply|review)$")
    timezone_offset_minutes: int = Field(default=0, ge=-840, le=840)


class PlanUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=500)
    exam_at: datetime
    daily_minutes: int = Field(ge=5, le=480)
    topic_order: list[str] = Field(min_length=1, max_length=200)
    regenerate: bool = False
    timezone_offset_minutes: int = Field(default=0, ge=-840, le=840)


class AttemptFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    learner_note: str | None = Field(default=None, max_length=2_000)
    appealed: bool | None = None


class AttemptFeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: str
    learner_note: str | None = None
    appealed: bool = False


class MasteryHistoryPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: str
    topic_id: str
    mastery: float = Field(ge=0.0, le=1.0)
    observed_at: datetime


class TopicInsight(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    topic_id: str
    topic_name: str
    mastery: float = Field(ge=0.0, le=1.0)
    attempt_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    last_practiced_at: datetime | None = None


class DueReviewInsight(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    topic_id: str
    topic_name: str
    due_at: datetime
    minutes: int = Field(ge=5, le=480)
    overdue: bool


class AttemptInsight(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_id: str
    question_id: str
    topic_id: str
    topic_name: str
    question_prompt: str
    answer: str
    is_correct: bool
    mastery: float = Field(ge=0.0, le=1.0)
    score: int = Field(ge=0, le=100)
    feedback: str
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    sources: list[SearchResult] = Field(default_factory=list)
    grounding: Grounding = Grounding.GENERAL
    grading_mode: str = "fallback"
    mastery_updated: bool = True
    observed_at: datetime
    learner_note: str | None = None
    appealed: bool = False


class LearningInsightsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str
    mastery_history: list[MasteryHistoryPoint]
    topics: list[TopicInsight]
    due_reviews: list[DueReviewInsight]
    attempts: list[AttemptInsight]


class ProgressResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str
    goal: str
    mastery: dict[str, float]
    stable: dict[str, bool]
    topics: dict[str, str]
    topic_order: list[str]
    diagnostic_count: int
    attempt_count: int
    plan_id: str | None = None


class LearningService:
    def __init__(
        self,
        projects: ProjectRepository,
        learning: LearningRepository,
        intelligence: LearningIntelligenceService | None = None,
        journey_events: JourneyEventRepository | None = None,
    ) -> None:
        self._projects = projects
        self._learning = learning
        self._intelligence = intelligence
        self._journey_events = journey_events

    def _require_project(self, owner_id: str, project_id: str) -> None:
        try:
            self._projects.get(owner_id, project_id)
        except RecordNotFoundError as error:
            raise ProjectNotFoundError("Project not found") from error

    @staticmethod
    def _progress(data: dict[str, Any]) -> dict[str, Any]:
        progress = data.get("progress")
        if not progress or not progress.get("seeded"):
            raise LearningNotSeededError("Learning project has not been seeded")
        return progress

    @staticmethod
    def _require_scope_fence(
        progress: dict[str, Any],
        expected_scope_fence: str | None,
    ) -> None:
        if (
            expected_scope_fence is not None
            and progress.get("_scope_fence") != expected_scope_fence
        ):
            raise LearningConflictError("Learning state belongs to a different operation scope")

    @staticmethod
    def _progress_response(data: dict[str, Any]) -> ProgressResponse:
        progress = LearningService._progress(data)
        plan = progress.get("plan")
        return ProgressResponse(
            workspace_id=data.get("workspace_id") or data["project_id"],
            goal=progress["goal"],
            mastery={
                topic_id: BKTState.model_validate(state).p_mastery
                for topic_id, state in progress["bkt_states"].items()
            },
            stable={
                topic_id: mastery_is_stable(BKTState.model_validate(state))
                for topic_id, state in progress["bkt_states"].items()
            },
            topics={
                topic_id: str(topic.get("name") or topic_id)
                for topic_id, topic in progress["topics"].items()
            },
            topic_order=list(progress.get("topic_order") or progress["topics"]),
            diagnostic_count=len(progress["diagnostic_runs"]),
            attempt_count=len(data["attempts"]),
            plan_id=plan["id"] if plan else None,
        )

    def seed(
        self,
        owner_id: str,
        project_id: str,
        payload: SeedRequest,
        *,
        answer_key_subjects: dict[str, str] | None = None,
    ) -> ProgressResponse:
        self._require_project(owner_id, project_id)
        topic_ids = [topic.id for topic in payload.topics]
        if len(topic_ids) != len(set(topic_ids)):
            raise LearningConflictError("Topic IDs must be unique")
        if payload.exam_at.tzinfo is None or payload.exam_at.utcoffset() is None:
            raise LearningConflictError("exam_at must be timezone-aware")
        resolved_subjects = (
            {topic.id: topic.name for topic in payload.topics}
            if answer_key_subjects is None
            else answer_key_subjects
        )
        if not set(resolved_subjects).issubset(topic_ids):
            raise LearningConflictError("Answer-key subjects must belong to seeded topics")
        normalized_subjects = {
            topic_id: subject.strip() for topic_id, subject in resolved_subjects.items()
        }
        if any(not subject or len(subject) > 200 for subject in normalized_subjects.values()):
            raise LearningConflictError("Answer-key subjects must contain 1 to 200 characters")

        def initialize(data: dict[str, Any]) -> dict[str, Any]:
            if data.get("attempts"):
                raise LearningConflictError("A project with attempts cannot be reseeded")
            data["progress"] = {
                "seeded": True,
                "goal": payload.goal.strip(),
                "exam_at": payload.exam_at.astimezone(UTC).isoformat(),
                "daily_minutes": payload.daily_minutes,
                "topics": {
                    topic.id: {
                        **topic.model_dump(mode="json"),
                        **(
                            {"answer_key_subject": normalized_subjects[topic.id]}
                            if topic.id in normalized_subjects
                            else {}
                        ),
                    }
                    for topic in payload.topics
                },
                "topic_order": [topic.id for topic in payload.topics],
                "bkt_states": {
                    topic.id: DEFAULT_BKT.model_dump(mode="json") for topic in payload.topics
                },
                "difficulty_states": {
                    topic.id: DifficultyState().model_dump(mode="json") for topic in payload.topics
                },
                "diagnostic_runs": [],
                "evidence": [],
                "pending_question": None,
                "question_sequence": 0,
                "question_history": {},
                "saved_questions": {},
                "question_requests": {},
                "plan": None,
            }
            return data

        record = self._learning.mutate(owner_id, project_id, initialize)
        return self._progress_response(record.data)

    def diagnose(
        self,
        owner_id: str,
        project_id: str,
        payload: DiagnosticRequest,
    ) -> ProgressResponse:
        self._require_project(owner_id, project_id)

        def apply_diagnostic(data: dict[str, Any]) -> dict[str, Any]:
            progress = self._progress(data)
            if progress["diagnostic_runs"]:
                return data
            seen_topics: set[str] = set()
            for result in payload.results:
                if result.topic_id in seen_topics:
                    raise LearningConflictError("Diagnostic topics must be unique")
                seen_topics.add(result.topic_id)
                if result.topic_id not in progress["topics"]:
                    raise LearningConflictError(f"Unknown topic: {result.topic_id}")
            if seen_topics != set(progress["topics"]):
                raise LearningConflictError("Initial diagnostic must cover every topic")
            for result in payload.results:
                state = BKTState.model_validate(progress["bkt_states"][result.topic_id])
                progress["bkt_states"][result.topic_id] = update_bkt(
                    state,
                    is_correct=result.is_correct,
                ).model_dump(mode="json")
                topic_name = str(progress["topics"][result.topic_id].get("name") or result.topic_id)
                evidence = create_evidence(
                    kind="diagnostic",
                    source_id=f"{project_id}:{payload.diagnostic_id}:{result.topic_id}",
                    summary=(
                        f"Initial check for {topic_name} "
                        f"{'met' if result.is_correct else 'did not yet meet'} the rubric."
                    ),
                    observed_at=datetime.now(UTC),
                    details={"topic_id": result.topic_id, "is_correct": result.is_correct},
                )
                progress["evidence"].append(evidence.model_dump(mode="json"))
            progress["diagnostic_runs"].append(payload.diagnostic_id)
            return data

        record = self._learning.mutate(owner_id, project_id, apply_diagnostic)
        return self._progress_response(record.data)

    def add_topic(
        self,
        owner_id: str,
        project_id: str,
        topic: TopicSeed,
        *,
        start_at: datetime | None = None,
    ) -> ProgressResponse:
        """Add one confirmed topic and regenerate its usable learning path."""

        self._require_project(owner_id, project_id)
        observed_at = (start_at or datetime.now(UTC)).astimezone(UTC)

        def apply(data: dict[str, Any]) -> dict[str, Any]:
            progress = self._progress(data)
            existing = progress["topics"].get(topic.id)
            if existing is not None:
                if str(existing.get("name", "")).casefold() != topic.name.casefold():
                    raise LearningConflictError("Topic ID already belongs to another topic")
                existing.setdefault("answer_key_subject", topic.name.strip())
                return data
            if any(
                str(item.get("name", "")).casefold() == topic.name.casefold()
                for item in progress["topics"].values()
            ):
                raise LearningConflictError("Learning topic already exists")
            if len(progress["topics"]) >= 200:
                raise LearningConflictError("Learning topic limit reached")

            progress["topics"][topic.id] = {
                **topic.model_dump(mode="json"),
                "answer_key_subject": topic.name.strip(),
            }
            progress.setdefault("topic_order", list(progress["topics"]))
            if topic.id not in progress["topic_order"]:
                progress["topic_order"].append(topic.id)
            progress["bkt_states"][topic.id] = DEFAULT_BKT.model_dump(mode="json")
            progress["difficulty_states"][topic.id] = DifficultyState().model_dump(mode="json")

            raw_plan = progress.get("plan")
            if raw_plan:
                try:
                    candidate = build_study_plan(
                        goal=progress["goal"],
                        topic_ids=list(progress["topic_order"]),
                        exam_at=datetime.fromisoformat(progress["exam_at"]),
                        daily_minutes=int(progress["daily_minutes"]),
                        start_at=observed_at,
                    )
                except ValueError as error:
                    raise LearningConflictError(str(error)) from error
                previous = StudyPlan.model_validate(raw_plan)
                completed = Counter(
                    (session.topic_id, session.activity)
                    for session in previous.sessions
                    if session.status == "completed"
                )
                sessions: list[StudySession] = []
                for session in candidate.sessions:
                    key = (session.topic_id, session.activity)
                    is_completed = completed[key] > 0
                    if is_completed:
                        completed[key] -= 1
                    sessions.append(
                        StudySession.model_validate(
                            {
                                **session.model_dump(mode="json"),
                                "status": "completed" if is_completed else "planned",
                            }
                        )
                    )
                progress["plan"] = StudyPlan.model_validate(
                    {**candidate.model_dump(mode="json"), "sessions": sessions}
                ).model_dump(mode="json")
            return data

        record = self._learning.mutate(owner_id, project_id, apply)
        return self._progress_response(record.data)

    def create_plan(
        self,
        owner_id: str,
        project_id: str,
        *,
        start_at: datetime | None = None,
    ) -> StudyPlan:
        self._require_project(owner_id, project_id)
        generated: StudyPlan | None = None

        def store_plan(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal generated
            progress = self._progress(data)
            if progress.get("plan"):
                generated = StudyPlan.model_validate(progress["plan"])
                return data
            generated = build_study_plan(
                goal=progress["goal"],
                topic_ids=list(progress["topics"]),
                exam_at=datetime.fromisoformat(progress["exam_at"]),
                daily_minutes=progress["daily_minutes"],
                start_at=start_at or datetime.now(UTC),
            )
            progress["plan"] = generated.model_dump(mode="json")
            return data

        self._learning.mutate(owner_id, project_id, store_plan)
        if generated is None:
            raise LearningServiceError("Plan generation failed")
        return generated

    @staticmethod
    def _assert_daily_capacity(
        plan_sessions: list[dict[str, Any]],
        *,
        target_id: str | None,
        new_planned_at: datetime,
        new_minutes: int,
        daily_minutes: int,
        tz_offset_minutes: int,
    ) -> None:
        """Reject a placement that would push a local calendar day over its budget.

        Every non-completed session is bucketed to its LOCAL date so the budget is
        measured on the day the learner actually sees, not on the UTC instant. The
        session identified by ``target_id`` is excluded because it is the one being
        moved or created; its new minutes are what we are trying to fit.
        """

        target_date = _local_date(new_planned_at, tz_offset_minutes)
        buckets: dict[date, int] = {}
        for session in plan_sessions:
            if session.get("status") == "completed":
                continue
            if target_id is not None and session.get("id") == target_id:
                continue
            planned_at = session["planned_at"]
            if isinstance(planned_at, str):
                planned_at = datetime.fromisoformat(planned_at)
            bucket = _local_date(planned_at, tz_offset_minutes)
            buckets[bucket] = buckets.get(bucket, 0) + int(session["minutes"])

        used = buckets.get(target_date, 0)
        if used + new_minutes <= daily_minutes:
            return

        # "The next open day" only means something when we are actually placing a
        # session. On the lower-the-budget path new_minutes is 0, so every day
        # would qualify — including days with no free capacity at all.
        next_free_date: str | None = None
        if 0 < new_minutes <= daily_minutes:
            candidate = target_date
            for _ in range(366):
                candidate += timedelta(days=1)
                if buckets.get(candidate, 0) + new_minutes <= daily_minutes:
                    next_free_date = candidate.isoformat()
                    break
        raise DailyCapacityExceededError(
            "This day would exceed the daily study budget.",
            detail={
                "date": target_date.isoformat(),
                "used": used,
                "requested": new_minutes,
                "daily_minutes": daily_minutes,
                "next_free_date": next_free_date,
            },
        )

    @classmethod
    def _displace_for_move(
        cls,
        plan: dict[str, Any],
        *,
        target_id: str,
        new_planned_at: datetime,
        new_minutes: int,
        tz_offset_minutes: int,
    ) -> None:
        """Make room on the destination day by pushing its pending work later.

        Sessions are displaced one local day at a time, cascading only as far as
        needed, so the daily budget stays true and no session is silently dropped.
        """

        daily_minutes = int(plan["daily_minutes"])
        target_date = _local_date(new_planned_at, tz_offset_minutes)
        # Reflowing must not push study work past the exam it is preparing for.
        raw_exam_at = plan.get("exam_at")
        exam_date: date | None = None
        if raw_exam_at:
            parsed_exam_at = (
                datetime.fromisoformat(raw_exam_at) if isinstance(raw_exam_at, str) else raw_exam_at
            )
            exam_date = _local_date(parsed_exam_at, tz_offset_minutes)

        def bucket_of(session: dict[str, Any]) -> date:
            planned_at = session["planned_at"]
            if isinstance(planned_at, str):
                planned_at = datetime.fromisoformat(planned_at)
            return _local_date(planned_at, tz_offset_minutes)

        def pending_on(day: date) -> list[dict[str, Any]]:
            return [
                item
                for item in plan["sessions"]
                if item.get("id") != target_id
                and item.get("status") != "completed"
                and bucket_of(item) == day
            ]

        # Work a day at a time, and keep pushing that day's latest session out
        # until it genuinely fits. Displacing only once leaves a day made of
        # several small sessions still over budget, which silently breaks the
        # very invariant this reflow exists to preserve.
        pending_days: list[tuple[date, int]] = [(target_date, new_minutes)]
        for _ in range(2_000):
            if not pending_days:
                return
            day, incoming = pending_days.pop(0)
            occupants = pending_on(day)
            used = sum(int(item["minutes"]) for item in occupants)
            if used + incoming <= daily_minutes:
                continue
            occupants.sort(key=lambda item: str(item["planned_at"]))
            displaced = occupants[-1]
            planned_at = displaced["planned_at"]
            if isinstance(planned_at, str):
                planned_at = datetime.fromisoformat(planned_at)
            moved_to = planned_at + timedelta(days=1)
            if exam_date is not None and _local_date(moved_to, tz_offset_minutes) > exam_date:
                raise DailyCapacityExceededError(
                    "Reflowing this move would push study work past the exam date.",
                    detail={
                        "date": target_date.isoformat(),
                        "used": sum(int(item["minutes"]) for item in pending_on(target_date)),
                        "requested": new_minutes,
                        "daily_minutes": daily_minutes,
                        "next_free_date": None,
                    },
                )
            displaced["planned_at"] = moved_to.isoformat()
            # Re-check this day (it may still be over), then the day that just
            # received the displaced session.
            pending_days.insert(0, (day, incoming))
            next_day = bucket_of(displaced)
            if not any(entry[0] == next_day for entry in pending_days):
                pending_days.append((next_day, 0))
        raise DailyCapacityExceededError(
            "The plan cannot absorb this move.",
            detail={
                "date": target_date.isoformat(),
                "used": sum(int(item["minutes"]) for item in pending_on(target_date)),
                "requested": new_minutes,
                "daily_minutes": daily_minutes,
                "next_free_date": None,
            },
        )

    def update_plan_session(
        self,
        owner_id: str,
        project_id: str,
        session_id: str,
        payload: PlanSessionUpdate,
        *,
        expected_version: int | None = None,
        displace_on_conflict: bool = False,
    ):
        self._require_project(owner_id, project_id)
        updated = None

        def apply(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal updated
            progress = self._progress(data)
            plan = progress.get("plan")
            if not plan and not payload.regenerate:
                raise LearningNotSeededError("Learning plan has not been created")
            for session in plan["sessions"]:
                if session["id"] != session_id:
                    continue
                if payload.planned_at is not None and (
                    payload.planned_at.tzinfo is None or payload.planned_at.utcoffset() is None
                ):
                    raise LearningConflictError("planned_at must be timezone-aware")
                new_status = payload.status if payload.status is not None else session["status"]
                if payload.planned_at is not None:
                    new_planned_at = payload.planned_at.astimezone(UTC)
                else:
                    new_planned_at = datetime.fromisoformat(session["planned_at"])
                new_minutes = payload.minutes if payload.minutes is not None else session["minutes"]
                moving_day = payload.planned_at is not None and _local_date(
                    new_planned_at, payload.timezone_offset_minutes
                ) != _local_date(
                    datetime.fromisoformat(session["planned_at"]),
                    payload.timezone_offset_minutes,
                )
                # Reopening a completed session restores work that already belongs
                # to that day; it adds no new load, and blocking it would leave a
                # mis-clicked "complete" with no way back.
                reopening_in_place = (
                    session["status"] == "completed"
                    and new_status != "completed"
                    and payload.planned_at is None
                    and payload.minutes is None
                )
                if new_status != "completed" and not reopening_in_place:
                    if moving_day and displace_on_conflict:
                        # Moving a session onto a day is a *move*, not an addition:
                        # a generated plan already fills every day to the budget, so
                        # requiring free space would make "move it to Saturday"
                        # permanently impossible. Push the day's existing pending
                        # work back to keep the budget true without dead-ending the
                        # learner.
                        self._displace_for_move(
                            plan,
                            target_id=session_id,
                            new_planned_at=new_planned_at,
                            new_minutes=new_minutes,
                            tz_offset_minutes=payload.timezone_offset_minutes,
                        )
                    else:
                        self._assert_daily_capacity(
                            plan["sessions"],
                            target_id=session_id,
                            new_planned_at=new_planned_at,
                            new_minutes=new_minutes,
                            daily_minutes=plan["daily_minutes"],
                            tz_offset_minutes=payload.timezone_offset_minutes,
                        )
                if payload.status is not None:
                    session["status"] = payload.status
                if payload.planned_at is not None:
                    session["planned_at"] = new_planned_at.isoformat()
                if payload.minutes is not None:
                    session["minutes"] = payload.minutes
                if payload.topic_id is not None:
                    if payload.topic_id not in progress["topics"]:
                        raise LearningConflictError("Unknown plan session topic")
                    session["topic_id"] = payload.topic_id
                    pending = progress.get("pending_question")
                    if (
                        pending
                        and pending.get("plan_session_id") == session_id
                        and pending.get("topic_id") != payload.topic_id
                    ):
                        progress["pending_question"] = None
                        pending_id = pending.get("id")
                        requests = progress.setdefault("question_requests", {})
                        for request_id, question_id in list(requests.items()):
                            if question_id == pending_id:
                                requests.pop(request_id, None)
                updated = deepcopy(session)
                return data
            raise LearningConflictError("Study session not found")

        with self._learning.plan_transaction(owner_id, project_id):
            if expected_version is not None:
                current = self._learning.get(owner_id, project_id)
                if current.version != expected_version:
                    raise LearningConflictError(
                        f"Expected learning version {expected_version}, found {current.version}"
                    )
            self._learning.mutate(owner_id, project_id, apply)
        if updated is None:
            raise LearningServiceError("Study session update failed")
        return StudySession.model_validate(updated)

    def add_plan_session(
        self, owner_id: str, project_id: str, payload: PlanSessionCreate
    ) -> StudySession:
        self._require_project(owner_id, project_id)
        if payload.planned_at.tzinfo is None or payload.planned_at.utcoffset() is None:
            raise LearningConflictError("planned_at must be timezone-aware")
        created = None

        def apply(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal created
            progress = self._progress(data)
            plan = progress.get("plan")
            if not plan:
                raise LearningNotSeededError("Learning plan has not been created")
            topic_id = stable_id("topic", project_id, payload.topic_name.strip())
            topic = progress["topics"].setdefault(
                topic_id,
                {
                    "id": topic_id,
                    "name": payload.topic_name.strip(),
                    "knowledge_type": KnowledgeType.CONCEPT.value,
                    "answer_key_subject": payload.topic_name.strip(),
                },
            )
            topic.setdefault("answer_key_subject", payload.topic_name.strip())
            progress["bkt_states"].setdefault(topic_id, DEFAULT_BKT.model_dump(mode="json"))
            progress["difficulty_states"].setdefault(
                topic_id, DifficultyState().model_dump(mode="json")
            )
            progress.setdefault("topic_order", list(progress["topics"]))
            if topic_id not in progress["topic_order"]:
                progress["topic_order"].append(topic_id)
            created = StudySession(
                id=stable_id(
                    "manual-session",
                    plan["id"],
                    topic_id,
                    payload.planned_at.isoformat(),
                    str(len(plan["sessions"])),
                ),
                topic_id=topic_id,
                planned_at=payload.planned_at,
                minutes=payload.minutes,
                activity=payload.activity,
            )
            self._assert_daily_capacity(
                plan["sessions"],
                target_id=None,
                new_planned_at=payload.planned_at,
                new_minutes=payload.minutes,
                daily_minutes=plan["daily_minutes"],
                tz_offset_minutes=payload.timezone_offset_minutes,
            )
            plan["sessions"].append(created.model_dump(mode="json"))
            return data

        with self._learning.plan_transaction(owner_id, project_id):
            self._learning.mutate(owner_id, project_id, apply)
        if created is None:
            raise LearningServiceError("Study session creation failed")
        return created

    def clear_plan(self, owner_id: str, project_id: str) -> None:
        """Clear calendar sessions while preserving learning state and materials."""
        self._require_project(owner_id, project_id)

        def apply(data: dict[str, Any]) -> dict[str, Any]:
            progress = self._progress(data)
            progress["plan"] = None
            return data

        with self._learning.plan_transaction(owner_id, project_id):
            self._learning.mutate(owner_id, project_id, apply)

    def update_plan(
        self,
        owner_id: str,
        project_id: str,
        payload: PlanUpdateRequest,
        *,
        start_at: datetime | None = None,
    ) -> StudyPlan:
        self._require_project(owner_id, project_id)
        if payload.exam_at.tzinfo is None or payload.exam_at.utcoffset() is None:
            raise LearningConflictError("exam_at must be timezone-aware")
        exam_at = payload.exam_at.astimezone(UTC)
        generated: StudyPlan | None = None

        def apply(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal generated
            progress = self._progress(data)
            plan = progress.get("plan")
            if not plan and not payload.regenerate:
                raise LearningNotSeededError("Learning plan has not been created")
            topic_ids = list(progress["topics"])
            if len(payload.topic_order) != len(set(payload.topic_order)) or set(
                payload.topic_order
            ) != set(topic_ids):
                raise LearningConflictError("topic_order must contain every learning topic once")

            normalized_goal = payload.goal.strip()
            observed_at = (start_at or datetime.now(UTC)).astimezone(UTC)
            try:
                candidate = build_study_plan(
                    goal=normalized_goal,
                    topic_ids=payload.topic_order,
                    exam_at=exam_at,
                    daily_minutes=payload.daily_minutes,
                    start_at=observed_at,
                )
            except ValueError as error:
                raise LearningConflictError(str(error)) from error

            existing = StudyPlan.model_validate(plan) if plan else None
            if payload.regenerate:
                completed_ids = {
                    session.id
                    for session in (existing.sessions if existing else [])
                    if session.status == "completed"
                }
                completed_kinds = Counter(
                    (session.topic_id, session.activity)
                    for session in (existing.sessions if existing else [])
                    if session.status == "completed"
                )
                sessions: list[StudySession] = []
                for session in candidate.sessions:
                    key = (session.topic_id, session.activity)
                    completed = session.id in completed_ids or completed_kinds[key] > 0
                    if completed and completed_kinds[key] > 0:
                        completed_kinds[key] -= 1
                    sessions.append(
                        StudySession.model_validate(
                            {
                                **session.model_dump(mode="json"),
                                "status": "completed" if completed else "planned",
                            }
                        )
                    )
                generated = StudyPlan.model_validate(
                    {**candidate.model_dump(mode="json"), "sessions": sessions}
                )
            else:
                if existing is None:
                    raise LearningNotSeededError("Learning plan has not been created")
                generated = StudyPlan.model_validate(
                    {
                        **existing.model_dump(mode="json"),
                        "goal": normalized_goal,
                        "exam_at": exam_at,
                        "daily_minutes": payload.daily_minutes,
                    }
                )
                if payload.daily_minutes < existing.daily_minutes:
                    # Preserved sessions were laid out for the old, higher budget;
                    # a lower budget must not silently overload any local day.
                    kept_sessions = generated.model_dump(mode="json")["sessions"]
                    checked: set[date] = set()
                    for session in kept_sessions:
                        if session.get("status") == "completed":
                            continue
                        planned_at = datetime.fromisoformat(session["planned_at"])
                        day = _local_date(planned_at, payload.timezone_offset_minutes)
                        if day in checked:
                            continue
                        checked.add(day)
                        self._assert_daily_capacity(
                            kept_sessions,
                            target_id=None,
                            new_planned_at=planned_at,
                            new_minutes=0,
                            daily_minutes=payload.daily_minutes,
                            tz_offset_minutes=payload.timezone_offset_minutes,
                        )

            progress["goal"] = normalized_goal
            progress["exam_at"] = exam_at.isoformat()
            progress["daily_minutes"] = payload.daily_minutes
            progress["topic_order"] = list(payload.topic_order)
            progress["plan"] = generated.model_dump(mode="json")
            return data

        self._learning.mutate(owner_id, project_id, apply)
        if generated is None:
            raise LearningServiceError("Plan update failed")
        return generated

    @staticmethod
    def _question_sources(question: dict[str, Any]) -> list[SearchResult]:
        grading = question.get("grading")
        if not isinstance(grading, dict):
            return []
        return [SearchResult.model_validate(source) for source in grading.get("sources", [])]

    @classmethod
    def _question_grounding(cls, question: dict[str, Any]) -> Grounding:
        stored = question.get("grounding")
        if stored is not None:
            return Grounding(stored)
        return Grounding.MATERIAL if cls._question_sources(question) else Grounding.GENERAL

    @classmethod
    def _is_material_question(cls, question: dict[str, Any]) -> bool:
        return cls._question_grounding(question) == Grounding.MATERIAL and bool(
            cls._question_sources(question)
        )

    def quarantine_ungrounded_pending(self, owner_id: str, project_id: str) -> bool:
        """Remove legacy general pending state from material-only workspaces."""

        changed = False
        with self._learning.question_transaction(owner_id, project_id):
            self._require_project(owner_id, project_id)
            current = self._learning.get(owner_id, project_id)
            progress = self._progress(current.data)
            pending = progress.get("pending_question")
            history = progress.get("question_history", {})
            requests = progress.get("question_requests", {})
            invalid_request_ids = {
                request_key
                for request_key, question_id in requests.items()
                if (question := history.get(question_id)) is not None
                and not self._is_material_question(question)
            }
            pending_is_invalid = pending is not None and not self._is_material_question(pending)
            if not pending_is_invalid and not invalid_request_ids:
                return False

            def quarantine(data: dict[str, Any]) -> dict[str, Any]:
                nonlocal changed
                inner_progress = self._progress(data)
                inner_pending = inner_progress.get("pending_question")
                if inner_pending is not None and not self._is_material_question(inner_pending):
                    inner_progress["pending_question"] = None
                    changed = True
                inner_history = inner_progress.get("question_history", {})
                inner_requests = inner_progress.get("question_requests", {})
                for request_key, question_id in list(inner_requests.items()):
                    question = inner_history.get(question_id)
                    if question is not None and not self._is_material_question(question):
                        inner_requests.pop(request_key, None)
                        changed = True
                return data

            self._learning.mutate(owner_id, project_id, quarantine)
        return changed

    @classmethod
    def _public_question(
        cls,
        question: dict[str, Any],
        *,
        saved_at: str | datetime | None = None,
        state_version: int = 0,
    ) -> QuestionResponse:
        return QuestionResponse(
            id=question["id"],
            topic_id=question["topic_id"],
            prompt=question["prompt"],
            explanation=(
                question.get("explanation") or (question.get("grading") or {}).get("explanation")
            ),
            difficulty_level=question.get("difficulty_level", 2),
            citations=question.get("citations", []),
            sources=cls._question_sources(question),
            grounding=cls._question_grounding(question),
            learning_mode=question.get("learning_mode", LearningMode.CONCEPT),
            mode=question.get("mode", "fallback"),
            saved=saved_at is not None,
            review_session_id=question.get("review_session_id"),
            plan_session_id=question.get("plan_session_id"),
            state_version=state_version,
            prompt_hash=stable_id("question-prompt", question["id"], question["prompt"]),
        )

    def next_question(
        self,
        owner_id: str,
        project_id: str,
        *,
        topic_id: str | None = None,
        difficulty_level: int | None = None,
        learning_mode: LearningMode = LearningMode.CONCEPT,
        replace_pending: bool = False,
        request_id: str | None = None,
        review_session_id: str | None = None,
        plan_session_id: str | None = None,
        require_material_grounding: bool = False,
        expected_scope_fence: str | None = None,
        scope_guard: Callable[[], None] | None = None,
    ) -> QuestionResponse:
        self._require_project(owner_id, project_id)
        if scope_guard is not None:
            scope_guard()
        if require_material_grounding:
            self.quarantine_ungrounded_pending(owner_id, project_id)

        def public_question(question: dict[str, Any], saved_at: str | None) -> QuestionResponse:
            # The state version at the moment the question is handed to the client
            # becomes the token the answer must echo, so a later regeneration that
            # advances the version fails the answer closed instead of grading a
            # different question than the learner saw.
            state_version = self._learning.get(owner_id, project_id).version
            response = self._public_question(
                question, saved_at=saved_at, state_version=state_version
            )
            if require_material_grounding and (
                response.grounding != Grounding.MATERIAL or not response.sources
            ):
                raise MaterialGroundingRequiredError(
                    "No uploaded material matches this topic; upload a relevant source and retry"
                )
            return response

        with self._learning.question_generation_lock(owner_id, project_id):
            current = self._learning.get(owner_id, project_id)
            snapshot_version = current.version
            progress = self._progress(current.data)
            self._require_scope_fence(progress, expected_scope_fence)
            history = progress.setdefault("question_history", {})
            requests = progress.setdefault("question_requests", {})
            if request_id and request_id in requests:
                replay = history.get(requests[request_id])
                if replay is not None:
                    return public_question(
                        replay,
                        progress.get("saved_questions", {}).get(replay["id"]),
                    )
            if progress.get("pending_question") and not replace_pending:
                pending = progress["pending_question"]
                return public_question(
                    pending,
                    progress.get("saved_questions", {}).get(pending["id"]),
                )
            session_topic_id: str | None = None
            originating_plan_session_id: str | None = None
            if plan_session_id is not None:
                raw_plan = progress.get("plan")
                plan_session = next(
                    (
                        session
                        for session in (raw_plan or {}).get("sessions", [])
                        if session.get("id") == plan_session_id
                    ),
                    None,
                )
                if plan_session is None:
                    raise LearningConflictError("Plan session not found")
                parsed_session = StudySession.model_validate(plan_session)
                if parsed_session.status == "completed":
                    raise LearningConflictError("Plan session is already completed")
                session_topic_id = parsed_session.topic_id
                originating_plan_session_id = parsed_session.id
                learning_mode = PLAN_ACTIVITY_MODES[parsed_session.activity]
                if topic_id is not None and topic_id != session_topic_id:
                    raise LearningConflictError("Plan session topic does not match")
            if review_session_id is not None:
                raw_plan = progress.get("plan")
                review_session = next(
                    (
                        session
                        for session in (raw_plan or {}).get("sessions", [])
                        if session.get("id") == review_session_id
                    ),
                    None,
                )
                if review_session is None:
                    raise LearningConflictError("Review session not found")
                parsed_review = StudySession.model_validate(review_session)
                if (
                    parsed_review.activity != "review"
                    or parsed_review.status == "completed"
                    or parsed_review.planned_at > datetime.now(UTC)
                ):
                    raise LearningConflictError("Review session is not due")
                session_topic_id = parsed_review.topic_id
                originating_plan_session_id = parsed_review.id
                learning_mode = LearningMode.EXAM
                if topic_id is not None and topic_id != session_topic_id:
                    raise LearningConflictError("Review session topic does not match")
            if topic_id is not None and topic_id not in progress["topics"]:
                raise LearningConflictError("Unknown practice topic")
            selected_topic_id = (
                session_topic_id
                or topic_id
                or min(
                    progress["topics"],
                    key=lambda candidate: (
                        BKTState.model_validate(progress["bkt_states"][candidate]).p_mastery,
                        candidate,
                    ),
                )
            )
            topic = progress["topics"][selected_topic_id]
            recent_question_prompts = [
                str(question.get("prompt") or "")
                for question in history.values()
                if question.get("topic_id") == selected_topic_id
            ][-5:]
            question_variation_index = int(progress.get("question_sequence", len(history)))
            mastery = BKTState.model_validate(progress["bkt_states"][selected_topic_id]).p_mastery
            selected_difficulty = (
                difficulty_level
                or DifficultyState.model_validate(
                    progress["difficulty_states"][selected_topic_id]
                ).level
            )
            if self._intelligence is not None:
                generated = self._intelligence.generate_question(
                    owner_id=owner_id,
                    workspace_id=project_id,
                    topic_id=selected_topic_id,
                    topic_name=topic["name"],
                    trusted_topic_subject=topic.get("answer_key_subject"),
                    mastery=mastery,
                    difficulty_level=selected_difficulty,
                    learning_mode=learning_mode,
                    prior_feedback=_recent_learning_needs(progress, selected_topic_id),
                    recent_question_prompts=recent_question_prompts,
                    variation_index=question_variation_index,
                )
            else:
                generated = fallback_question(
                    topic_id=selected_topic_id,
                    topic_name=topic["name"],
                    difficulty_level=selected_difficulty,
                    sources=[],
                    learning_mode=learning_mode,
                    variation_index=question_variation_index,
                )
            if require_material_grounding and (
                generated.grounding != Grounding.MATERIAL or not generated.sources
            ):
                raise MaterialGroundingRequiredError(
                    "No uploaded material matches this topic; upload a relevant source and retry"
                )
            proposed = {
                "topic_id": selected_topic_id,
                "prompt": generated.prompt,
                "explanation": generated.explanation,
                "expected_answer": generated.expected_answer,
                "difficulty_level": generated.difficulty_level,
                "learning_mode": generated.learning_mode.value,
                "citations": generated.citations,
                "grounding": generated.grounding.value,
                "mode": generated.mode,
                "grading": generated.model_dump(mode="json"),
                "review_session_id": review_session_id,
                "plan_session_id": originating_plan_session_id,
            }
            selected: dict[str, Any] | None = None
            selected_saved_at: str | None = None

            def store_once(data: dict[str, Any]) -> dict[str, Any]:
                nonlocal selected
                inner_progress = self._progress(data)
                self._require_scope_fence(inner_progress, expected_scope_fence)
                inner_history = inner_progress.setdefault("question_history", {})
                sequence = int(inner_progress.get("question_sequence", len(inner_history)))
                question_id = stable_id("question", project_id, selected_topic_id, str(sequence))
                while question_id in inner_history:
                    sequence += 1
                    question_id = stable_id(
                        "question", project_id, selected_topic_id, str(sequence)
                    )
                selected = {"id": question_id, **proposed}
                inner_progress["question_sequence"] = sequence + 1
                inner_progress["pending_question"] = selected
                inner_history[question_id] = deepcopy(selected)
                saved = inner_progress.setdefault("saved_questions", {})
                while len(inner_history) > MAX_QUESTION_HISTORY:
                    removable = next(
                        (
                            candidate
                            for candidate in inner_history
                            if candidate != question_id and candidate not in saved
                        ),
                        None,
                    )
                    if removable is None:
                        raise LearningConflictError("Practice history limit reached")
                    inner_history.pop(removable, None)
                if request_id:
                    inner_requests = inner_progress.setdefault("question_requests", {})
                    inner_requests[request_id] = question_id
                    while len(inner_requests) > MAX_QUESTION_REQUESTS:
                        inner_requests.pop(next(iter(inner_requests)))
                return data

            with self._learning.question_transaction(owner_id, project_id):
                if scope_guard is not None:
                    scope_guard()
                latest = self._learning.get(owner_id, project_id)
                latest_progress = self._progress(latest.data)
                self._require_scope_fence(latest_progress, expected_scope_fence)
                latest_history = latest_progress.setdefault("question_history", {})
                if request_id:
                    latest_requests = latest_progress.setdefault("question_requests", {})
                    replay_id = latest_requests.get(request_id)
                    replay = latest_history.get(replay_id) if replay_id else None
                    if replay is not None:
                        selected = deepcopy(replay)
                        selected_saved_at = latest_progress.get("saved_questions", {}).get(
                            replay["id"]
                        )
                if selected is None and latest.version != snapshot_version:
                    pending = latest_progress.get("pending_question")
                    if pending is not None and not replace_pending:
                        selected = deepcopy(pending)
                        selected_saved_at = latest_progress.get("saved_questions", {}).get(
                            pending["id"]
                        )
                    else:
                        raise LearningConflictError(
                            "Learning state changed during question generation"
                        )
                if selected is None:
                    self._learning.mutate(owner_id, project_id, store_once)
            if selected is None:
                raise LearningServiceError("Question generation failed")
            self.try_record_journey_event(
                owner_id,
                project_id,
                name="question_started",
                idempotency_key=selected["id"],
                ref_id=selected["id"],
            )
            return public_question(selected, selected_saved_at)

    def pending_question(
        self,
        owner_id: str,
        project_id: str,
        *,
        require_material_grounding: bool = False,
    ) -> QuestionResponse:
        self._require_project(owner_id, project_id)
        if require_material_grounding:
            self.quarantine_ungrounded_pending(owner_id, project_id)
        progress = self._progress(self._learning.get(owner_id, project_id).data)
        pending = progress.get("pending_question")
        if pending is None:
            raise QuestionNotFoundError("No pending practice question")
        return self._public_question(
            pending,
            saved_at=progress.get("saved_questions", {}).get(pending["id"]),
        )

    def retry_question(
        self,
        owner_id: str,
        project_id: str,
        question_id: str,
        *,
        require_material_grounding: bool = False,
    ) -> QuestionResponse:
        self._require_project(owner_id, project_id)
        selected: dict[str, Any] | None = None
        saved_at: str | None = None

        def restore(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal saved_at, selected
            progress = self._progress(data)
            history = progress.setdefault("question_history", {})
            stored_question = history.get(question_id)
            if stored_question is None:
                stored_question = next(
                    (
                        attempt["question_snapshot"]
                        for attempt in data.get("attempts", {}).values()
                        if attempt.get("question_id") == question_id
                        and attempt.get("question_snapshot") is not None
                    ),
                    None,
                )
            if stored_question is None:
                raise QuestionNotFoundError("Practice question not found")
            if require_material_grounding and not self._is_material_question(stored_question):
                raise MaterialGroundingRequiredError(
                    "This legacy question is not grounded in uploaded material; start a new task"
                )
            selected = deepcopy(stored_question)
            selected.pop("review_session_id", None)
            selected.pop("plan_session_id", None)
            progress["pending_question"] = deepcopy(selected)
            saved_at = progress.get("saved_questions", {}).get(question_id)
            return data

        self._learning.mutate(owner_id, project_id, restore)
        if selected is None:
            raise QuestionNotFoundError("Practice question not found")
        return self._public_question(selected, saved_at=saved_at)

    def set_question_saved(
        self,
        owner_id: str,
        project_id: str,
        question_id: str,
        payload: QuestionSaveRequest,
    ) -> SavedQuestionResponse:
        self._require_project(owner_id, project_id)
        selected: dict[str, Any] | None = None
        saved_at: str | None = None

        def apply(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal saved_at, selected
            progress = self._progress(data)
            history = progress.setdefault("question_history", {})
            pending = progress.get("pending_question")
            if question_id not in history and pending and pending.get("id") == question_id:
                history[question_id] = deepcopy(pending)
            selected = history.get(question_id)
            if selected is None:
                raise LearningConflictError("Practice question not found")
            saved_questions = progress.setdefault("saved_questions", {})
            if payload.saved:
                if (
                    question_id not in saved_questions
                    and len(saved_questions) >= MAX_SAVED_QUESTIONS
                ):
                    raise LearningConflictError("Saved question limit reached")
                saved_at = saved_questions.get(question_id) or datetime.now(UTC).isoformat()
                saved_questions[question_id] = saved_at
            else:
                saved_questions.pop(question_id, None)
                saved_at = None
            return data

        self._learning.mutate(owner_id, project_id, apply)
        if selected is None:
            raise LearningServiceError("Question save failed")
        public = self._public_question(selected, saved_at=saved_at)
        return SavedQuestionResponse.model_validate(
            {**public.model_dump(mode="json"), "saved_at": saved_at}
        )

    def saved_questions(
        self,
        owner_id: str,
        project_id: str,
    ) -> list[SavedQuestionResponse]:
        self._require_project(owner_id, project_id)
        progress = self._progress(self._learning.get(owner_id, project_id).data)
        history = progress.get("question_history", {})
        saved = progress.get("saved_questions", {})
        responses: list[SavedQuestionResponse] = []
        for question_id, saved_at in sorted(
            saved.items(),
            key=lambda item: item[1],
            reverse=True,
        ):
            question = history.get(question_id)
            if question is None:
                continue
            public = self._public_question(question, saved_at=saved_at)
            responses.append(
                SavedQuestionResponse.model_validate(
                    {**public.model_dump(mode="json"), "saved_at": saved_at}
                )
            )
        return responses

    def submit_answer(
        self,
        owner_id: str,
        project_id: str,
        payload: AnswerRequest,
        *,
        require_material_grounding: bool = False,
        expected_scope_fence: str | None = None,
        scope_guard: Callable[[], None] | None = None,
    ) -> AnswerResponse:
        self._require_project(owner_id, project_id)
        if scope_guard is not None:
            scope_guard()
        current = self._learning.get(owner_id, project_id)
        current_progress = self._progress(current.data)
        self._require_scope_fence(current_progress, expected_scope_fence)
        if payload.attempt_id in current.data["attempts"]:
            stored_attempt = current.data["attempts"][payload.attempt_id]
            stored_grounding = stored_attempt.get("grounding") or (
                Grounding.MATERIAL.value
                if stored_attempt.get("sources")
                else Grounding.GENERAL.value
            )
            response = AnswerResponse.model_validate(
                {**stored_attempt, "grounding": stored_grounding, "replayed": True}
            )
            if response.grounding == Grounding.MATERIAL:
                self.try_record_journey_event(
                    owner_id,
                    project_id,
                    name="grounded_grade_created",
                    idempotency_key=payload.attempt_id,
                    occurred_at=response.observed_at,
                    ref_id=payload.attempt_id,
                )
            return response
        current_question = current_progress.get("pending_question")
        if current_question is None or current_question["id"] != payload.question_id:
            raise LearningConflictError("Question is not pending")
        if require_material_grounding and not self._is_material_question(current_question):
            self.quarantine_ungrounded_pending(owner_id, project_id)
            raise MaterialGroundingRequiredError(
                "This legacy question is not grounded in uploaded material; start a new task"
            )
        if "grading" in current_question:
            generated = GeneratedQuestion.model_validate(current_question["grading"])
            current_subject = str(
                current_progress["topics"][generated.topic_id].get("answer_key_subject") or ""
            ).strip()
            if not current_subject or current_subject != (generated.answer_key_subject or ""):
                generated = generated.model_copy(
                    update={
                        "expected_answer": "",
                        "answer_key_trusted": False,
                        "answer_key_subject": None,
                    }
                )
            grade = (
                self._intelligence.grade_answer(
                    owner_id=owner_id,
                    question=generated,
                    answer=payload.answer,
                )
                if self._intelligence is not None
                else fallback_grade(generated, payload.answer)
            )
        else:
            generated = fallback_question(
                topic_id=current_question["topic_id"],
                topic_name=current_question["expected_answer"],
                difficulty_level=2,
                sources=[],
            )
            grade = fallback_grade(generated, payload.answer)
        result: dict[str, Any] | None = None
        replayed = False
        next_review_at: datetime | None = None
        completed_review_session_id: str | None = None
        completed_plan_session_id: str | None = None

        def grade_once(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal completed_plan_session_id, completed_review_session_id
            nonlocal next_review_at, replayed, result
            progress = self._progress(data)
            self._require_scope_fence(progress, expected_scope_fence)
            if payload.attempt_id in data["attempts"]:
                replayed = True
                result = deepcopy(data["attempts"][payload.attempt_id])
                return data
            question = progress.get("pending_question")
            if question is None or question["id"] != payload.question_id:
                raise LearningConflictError("Question is not pending")

            is_correct = grade.passed
            topic_id = question["topic_id"]
            topic_name = str(progress["topics"][topic_id].get("name") or topic_id)
            learning_mode = str(question.get("learning_mode") or LearningMode.CONCEPT.value)
            current_bkt = BKTState.model_validate(progress["bkt_states"][topic_id])
            current_difficulty = DifficultyState.model_validate(
                progress["difficulty_states"][topic_id]
            )
            already_credited = payload.question_id in current_bkt.credited_question_ids or any(
                attempt.get("question_id") == payload.question_id
                and bool(attempt.get("mastery_updated", True))
                for attempt in data["attempts"].values()
            )
            grading = (question.get("grading") or {}) if isinstance(question, dict) else {}
            grading_subject = str(grading.get("answer_key_subject") or "").strip()
            current_subject = str(
                progress["topics"][topic_id].get("answer_key_subject") or ""
            ).strip()
            mastery_updated = (
                grade.mastery_evidence
                and bool(grading_subject)
                and grading_subject == current_subject
                and not already_credited
            )
            if mastery_updated:
                bkt_state = update_bkt(current_bkt, is_correct=is_correct).model_copy(
                    update={
                        "credited_question_ids": [
                            *current_bkt.credited_question_ids,
                            payload.question_id,
                        ][-MAX_CREDITED_QUESTIONS:]
                    }
                )
            else:
                bkt_state = current_bkt
            difficulty = (
                update_difficulty(
                    current_difficulty,
                    is_correct=is_correct,
                    question_id=payload.question_id,
                )
                if mastery_updated
                else current_difficulty
            )
            observed_at = datetime.now(UTC)
            evidence = create_evidence(
                kind="attempt",
                source_id=payload.attempt_id,
                summary=(
                    f"Completed a {learning_mode} learning task for {topic_name}; "
                    f"the response {'met' if is_correct else 'did not yet meet'} the rubric."
                ),
                observed_at=observed_at,
                details={
                    "topic_id": topic_id,
                    "question_id": payload.question_id,
                    "is_correct": is_correct,
                    "score": grade.score,
                    "feedback": grade.feedback,
                    "strengths": grade.strengths,
                    "gaps": grade.gaps,
                    "misconceptions": grade.misconceptions,
                    "citations": grade.citations,
                    "grading_mode": grade.mode,
                    "mastery_updated": mastery_updated,
                },
            )
            raw_plan = progress.get("plan")
            if raw_plan and mastery_updated:
                originating_session_id = question.get("plan_session_id") or question.get(
                    "review_session_id"
                )
                if originating_session_id is not None:
                    originating_session = next(
                        (
                            session
                            for session in raw_plan["sessions"]
                            if session.get("id") == originating_session_id
                        ),
                        None,
                    )
                    if originating_session is None:
                        raise LearningConflictError("Plan session not found")
                    if originating_session.get("topic_id") != topic_id:
                        raise LearningConflictError("Plan session topic does not match")
                    originating_session["status"] = "completed"
                    completed_plan_session_id = originating_session_id
                    if originating_session.get("activity") == "review":
                        completed_review_session_id = originating_session_id
                candidate_review_at = observed_at + timedelta(days=3 if is_correct else 1)
                exam_at = datetime.fromisoformat(progress["exam_at"])
                if candidate_review_at < exam_at:
                    review_session = StudySession(
                        id=stable_id("review", project_id, payload.attempt_id),
                        topic_id=topic_id,
                        planned_at=candidate_review_at,
                        minutes=min(30, int(progress["daily_minutes"])),
                        activity="review",
                    )
                    next_review_at = _upsert_review_session(
                        raw_plan, review_session, not_before=observed_at
                    )

            result = {
                "attempt_id": payload.attempt_id,
                "question_id": payload.question_id,
                "topic_id": topic_id,
                "is_correct": is_correct,
                "mastery": bkt_state.p_mastery,
                "difficulty_level": difficulty.level,
                "evidence_id": evidence.id,
                "score": grade.score,
                "feedback": grade.feedback,
                "strengths": grade.strengths,
                "gaps": grade.gaps,
                "misconceptions": grade.misconceptions,
                "citations": grade.citations,
                "sources": [
                    source.model_dump(mode="json") for source in self._question_sources(question)
                ],
                "grounding": self._question_grounding(question).value,
                "grading_mode": grade.mode,
                "reason_code": grade.reason_code,
                "mastery_updated": mastery_updated,
                "next_review_at": (
                    next_review_at.isoformat() if next_review_at is not None else None
                ),
                "answer": payload.answer,
                "observed_at": observed_at.isoformat(),
                "completed_review_session_id": completed_review_session_id,
                "completed_plan_session_id": completed_plan_session_id,
                "session_decision": decide_next_session_action(
                    current_topic_id=topic_id,
                    current_mastery=bkt_state.p_mastery,
                    difficulty_level=difficulty.level,
                    topic_order=list(progress.get("topic_order") or progress["topics"].keys()),
                    mastery_by_topic={
                        candidate_id: (
                            bkt_state.p_mastery
                            if candidate_id == topic_id
                            else BKTState.model_validate(candidate_state).p_mastery
                        )
                        for candidate_id, candidate_state in progress["bkt_states"].items()
                    },
                    remaining_minutes=payload.remaining_minutes,
                    reserve_minutes=(
                        payload.summary_reserve_minutes
                        or summary_reserve_minutes(int(progress["daily_minutes"]))
                    ),
                ).__dict__,
                "question_snapshot": deepcopy(question),
            }
            data["attempts"][payload.attempt_id] = deepcopy(result)
            progress["bkt_states"][topic_id] = bkt_state.model_dump(mode="json")
            progress["difficulty_states"][topic_id] = difficulty.model_dump(mode="json")
            progress["evidence"].append(evidence.model_dump(mode="json"))
            progress["pending_question"] = None
            return data

        with self._learning.plan_transaction(owner_id, project_id):
            if scope_guard is not None:
                scope_guard()
            # The fence must identify the *question*, not the learning record as a
            # whole: the record version also advances on unrelated writes (saving a
            # question, completing a plan session, a second tab), and it is not
            # carried by every question producer. prompt_hash is stable across all
            # of those and changes exactly when the pending question changes, so it
            # is the token that fails a superseded answer closed.
            if payload.prompt_hash is not None:
                current = self._learning.get(owner_id, project_id)
                is_replay = payload.attempt_id in current.data.get("attempts", {})
                if not is_replay:
                    pending = self._progress(current.data).get("pending_question")
                    if (
                        pending is not None
                        and stable_id("question-prompt", pending["id"], pending["prompt"])
                        != payload.prompt_hash
                    ):
                        raise LearningConflictError(
                            "Question state changed before grading; reload the current question"
                        )
            self._learning.mutate(owner_id, project_id, grade_once)
        if result is None:
            raise LearningServiceError("Answer grading failed")
        if result["grounding"] == Grounding.MATERIAL.value:
            self.try_record_journey_event(
                owner_id,
                project_id,
                name="grounded_grade_created",
                idempotency_key=payload.attempt_id,
                occurred_at=datetime.fromisoformat(result["observed_at"]),
                ref_id=payload.attempt_id,
            )
        return AnswerResponse.model_validate({**result, "replayed": replayed})

    def update_attempt_feedback(
        self,
        owner_id: str,
        project_id: str,
        attempt_id: str,
        payload: AttemptFeedbackRequest,
    ) -> AttemptFeedbackResponse:
        self._require_project(owner_id, project_id)
        response: AttemptFeedbackResponse | None = None

        def apply(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal response
            attempt = data.get("attempts", {}).get(attempt_id)
            if attempt is None:
                raise AttemptNotFoundError("Learning attempt not found")
            if payload.learner_note is not None:
                attempt["learner_note"] = payload.learner_note.strip() or None
            if payload.appealed is not None:
                attempt["appealed"] = payload.appealed
            response = AttemptFeedbackResponse(
                attempt_id=attempt_id,
                learner_note=attempt.get("learner_note"),
                appealed=bool(attempt.get("appealed", False)),
            )
            return data

        self._learning.mutate(owner_id, project_id, apply)
        if response is None:
            raise AttemptNotFoundError("Learning attempt not found")
        return response

    def insights(
        self,
        owner_id: str,
        project_id: str,
        *,
        now: datetime | None = None,
    ) -> LearningInsightsResponse:
        self._require_project(owner_id, project_id)
        record = self._learning.get(owner_id, project_id)
        progress = self._progress(record.data)
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        history = progress.get("question_history", {})
        evidence_times = {
            item["source_id"]: datetime.fromisoformat(item["observed_at"])
            for item in progress.get("evidence", [])
            if item.get("kind") == "attempt"
        }
        attempts: list[AttemptInsight] = []
        for attempt_id, attempt in record.data.get("attempts", {}).items():
            question = (
                history.get(attempt.get("question_id")) or attempt.get("question_snapshot") or {}
            )
            attempt_time = (
                datetime.fromisoformat(attempt["observed_at"])
                if attempt.get("observed_at")
                else evidence_times.get(attempt_id, observed_at)
            )
            topic_id = str(attempt["topic_id"])
            topic_name = str(progress["topics"][topic_id].get("name") or topic_id)
            attempts.append(
                AttemptInsight(
                    attempt_id=attempt_id,
                    question_id=str(attempt["question_id"]),
                    topic_id=topic_id,
                    topic_name=topic_name,
                    question_prompt=str(question.get("prompt") or ""),
                    answer=str(attempt.get("answer") or ""),
                    is_correct=bool(attempt["is_correct"]),
                    mastery=float(attempt["mastery"]),
                    score=int(attempt.get("score", 0)),
                    feedback=str(attempt.get("feedback") or ""),
                    strengths=list(attempt.get("strengths", [])),
                    gaps=list(attempt.get("gaps", [])),
                    misconceptions=list(attempt.get("misconceptions", [])),
                    citations=list(attempt.get("citations", [])),
                    sources=[
                        SearchResult.model_validate(source) for source in attempt.get("sources", [])
                    ],
                    grounding=attempt.get("grounding", Grounding.GENERAL),
                    grading_mode=str(attempt.get("grading_mode") or "fallback"),
                    mastery_updated=bool(attempt.get("mastery_updated", True)),
                    observed_at=attempt_time,
                    learner_note=attempt.get("learner_note"),
                    appealed=bool(attempt.get("appealed", False)),
                )
            )
        attempts.sort(key=lambda item: (item.observed_at, item.attempt_id), reverse=True)
        chronological = list(reversed(attempts))

        topics: list[TopicInsight] = []
        for topic_id in progress.get("topic_order") or progress["topics"]:
            topic_attempts = [item for item in attempts if item.topic_id == topic_id]
            topics.append(
                TopicInsight(
                    topic_id=topic_id,
                    topic_name=str(progress["topics"][topic_id].get("name") or topic_id),
                    mastery=BKTState.model_validate(progress["bkt_states"][topic_id]).p_mastery,
                    attempt_count=len(topic_attempts),
                    error_count=sum(not item.is_correct for item in topic_attempts),
                    last_practiced_at=(
                        max(item.observed_at for item in topic_attempts) if topic_attempts else None
                    ),
                )
            )

        due_reviews: list[DueReviewInsight] = []
        for raw_session in (progress.get("plan") or {}).get("sessions", []):
            session = StudySession.model_validate(raw_session)
            if (
                session.activity != "review"
                or session.status == "completed"
                or session.planned_at > observed_at
            ):
                continue
            topic_name = str(
                progress["topics"].get(session.topic_id, {}).get("name") or session.topic_id
            )
            due_reviews.append(
                DueReviewInsight(
                    session_id=session.id,
                    topic_id=session.topic_id,
                    topic_name=topic_name,
                    due_at=session.planned_at,
                    minutes=session.minutes,
                    overdue=session.planned_at < observed_at,
                )
            )
        due_reviews.sort(key=lambda item: (item.due_at, item.session_id))
        unique_due_reviews: dict[str, DueReviewInsight] = {}
        for review in due_reviews:
            unique_due_reviews.setdefault(review.topic_id, review)
        due_reviews = list(unique_due_reviews.values())[:MAX_REVIEW_SESSIONS]
        return LearningInsightsResponse(
            workspace_id=record.data.get("workspace_id") or record.data["project_id"],
            mastery_history=[
                MasteryHistoryPoint(
                    attempt_id=item.attempt_id,
                    topic_id=item.topic_id,
                    mastery=item.mastery,
                    observed_at=item.observed_at,
                )
                for item in chronological
            ],
            topics=topics,
            due_reviews=due_reviews,
            attempts=attempts,
        )

    def progress(self, owner_id: str, project_id: str) -> ProgressResponse:
        self._require_project(owner_id, project_id)
        return self._progress_response(self._learning.get(owner_id, project_id).data)

    def record_journey_event(
        self,
        owner_id: str,
        project_id: str,
        *,
        name: JourneyEventName,
        idempotency_key: str,
        occurred_at: datetime | None = None,
        ref_id: str | None = None,
    ) -> JourneyEvent:
        if self._journey_events is None:
            raise LearningServiceError("Journey event storage is unavailable")
        proposed = build_journey_event(
            workspace_id=project_id,
            name=name,
            idempotency_key=idempotency_key,
            occurred_at=occurred_at or datetime.now(UTC),
            ref_id=ref_id,
        )
        with self._learning.plan_transaction(owner_id, project_id):
            self._require_project(owner_id, project_id)
            return self._journey_events.append(owner_id, project_id, proposed)

    def try_record_journey_event(
        self,
        owner_id: str,
        project_id: str,
        *,
        name: JourneyEventName,
        idempotency_key: str,
        occurred_at: datetime | None = None,
        ref_id: str | None = None,
    ) -> JourneyEvent | None:
        if self._journey_events is None:
            return None
        try:
            return self.record_journey_event(
                owner_id,
                project_id,
                name=name,
                idempotency_key=idempotency_key,
                occurred_at=occurred_at,
                ref_id=ref_id,
            )
        except Exception as error:
            logger.warning(
                "event=journey_event_write_failed name=%s reason=%s",
                name,
                type(error).__name__,
            )
            return None

    def mark_grounded_grade_shown(
        self,
        owner_id: str,
        project_id: str,
        attempt_id: str,
        *,
        occurred_at: datetime | None = None,
    ) -> JourneyEvent:
        proposed = build_journey_event(
            workspace_id=project_id,
            name="grounded_grade_shown",
            idempotency_key=attempt_id,
            occurred_at=occurred_at or datetime.now(UTC),
            ref_id=attempt_id,
        )
        if self._journey_events is None:
            raise LearningServiceError("Journey event storage is unavailable")
        with self._learning.plan_transaction(owner_id, project_id):
            self._require_project(owner_id, project_id)
            current = self._learning.get(owner_id, project_id).data
            attempt = current.get("attempts", {}).get(attempt_id)
            if attempt is None:
                raise AttemptNotFoundError("Learning attempt not found")
            if attempt.get("grounding") != Grounding.MATERIAL.value:
                raise LearningConflictError("Only a material-grounded grade can be shown")
            return self._journey_events.append(owner_id, project_id, proposed)

    def snapshot_journey_events(
        self,
        owner_id: str,
        project_id: str,
    ) -> StoredRecord | None:
        if self._journey_events is None:
            return None
        return self._journey_events.snapshot(owner_id, project_id)

    def restore_journey_events(
        self,
        owner_id: str,
        project_id: str,
        record: StoredRecord,
    ) -> None:
        if self._journey_events is not None:
            self._journey_events.restore(owner_id, project_id, record)

    def delete_journey_events(self, owner_id: str, project_id: str) -> None:
        if self._journey_events is not None:
            self._journey_events.delete(owner_id, project_id)

    def evidence(self, owner_id: str, project_id: str) -> list[LearningEvidence]:
        self._require_project(owner_id, project_id)
        progress = self._progress(self._learning.get(owner_id, project_id).data)
        return [LearningEvidence.model_validate(item) for item in progress["evidence"]]
