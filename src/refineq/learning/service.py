"""Application service for the deterministic learning journey."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from refineq.knowledge.index import SearchResult
from refineq.learning.bkt import DEFAULT_BKT, update_bkt
from refineq.learning.difficulty import update_difficulty
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
from refineq.learning.planning import build_study_plan
from refineq.storage.json_store import RecordNotFoundError
from refineq.storage.learning import LearningRepository
from refineq.storage.projects import ProjectRepository

MAX_QUESTION_HISTORY = 200
MAX_SAVED_QUESTIONS = 100
MAX_QUESTION_REQUESTS = 100


class LearningServiceError(RuntimeError):
    code = "learning_error"


class ProjectNotFoundError(LearningServiceError):
    code = "project_not_found"


class LearningNotSeededError(LearningServiceError):
    code = "learning_not_seeded"


class LearningConflictError(LearningServiceError):
    code = "learning_conflict"


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

    diagnostic_id: str = Field(
        default="initial",
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$",
    )
    results: list[DiagnosticResultInput] = Field(min_length=1, max_length=200)


class QuestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    topic_id: str
    prompt: str
    difficulty_level: int = Field(default=2, ge=1, le=5)
    citations: list[str] = Field(default_factory=list)
    sources: list[SearchResult] = Field(default_factory=list)
    grounding: Grounding = Grounding.GENERAL
    learning_mode: LearningMode = LearningMode.CONCEPT
    mode: str = "fallback"
    saved: bool = False


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


class AnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attempt_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    question_id: str = Field(min_length=1)
    answer: str = Field(min_length=1, max_length=10_000)


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
    mastery_updated: bool = True
    next_review_at: datetime | None = None
    answer: str = ""
    observed_at: datetime | None = None
    learner_note: str | None = None
    appealed: bool = False
    completed_review_session_id: str | None = None
    question_snapshot: dict[str, Any] | None = Field(default=None, exclude=True)
    replayed: bool = False


class PlanSessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = Field(default=None, pattern=r"^(planned|completed)$")
    planned_at: datetime | None = None
    minutes: int | None = Field(default=None, ge=5, le=480)


class PlanUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=500)
    exam_at: datetime
    daily_minutes: int = Field(ge=5, le=480)
    topic_order: list[str] = Field(min_length=1, max_length=200)
    regenerate: bool = False


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
    ) -> None:
        self._projects = projects
        self._learning = learning
        self._intelligence = intelligence

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
    ) -> ProgressResponse:
        self._require_project(owner_id, project_id)
        topic_ids = [topic.id for topic in payload.topics]
        if len(topic_ids) != len(set(topic_ids)):
            raise LearningConflictError("Topic IDs must be unique")
        if payload.exam_at.tzinfo is None or payload.exam_at.utcoffset() is None:
            raise LearningConflictError("exam_at must be timezone-aware")

        def initialize(data: dict[str, Any]) -> dict[str, Any]:
            if data.get("attempts"):
                raise LearningConflictError("A project with attempts cannot be reseeded")
            data["progress"] = {
                "seeded": True,
                "goal": payload.goal.strip(),
                "exam_at": payload.exam_at.astimezone(UTC).isoformat(),
                "daily_minutes": payload.daily_minutes,
                "topics": {topic.id: topic.model_dump(mode="json") for topic in payload.topics},
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
            if payload.diagnostic_id in progress["diagnostic_runs"]:
                return data
            seen_topics: set[str] = set()
            for result in payload.results:
                if result.topic_id in seen_topics:
                    raise LearningConflictError("Diagnostic topics must be unique")
                seen_topics.add(result.topic_id)
                if result.topic_id not in progress["topics"]:
                    raise LearningConflictError(f"Unknown topic: {result.topic_id}")
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

    def update_plan_session(
        self,
        owner_id: str,
        project_id: str,
        session_id: str,
        payload: PlanSessionUpdate,
    ):
        self._require_project(owner_id, project_id)
        updated = None

        def apply(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal updated
            progress = self._progress(data)
            plan = progress.get("plan")
            if not plan:
                raise LearningNotSeededError("Learning plan has not been created")
            for session in plan["sessions"]:
                if session["id"] != session_id:
                    continue
                if payload.status is not None:
                    session["status"] = payload.status
                if payload.planned_at is not None:
                    if payload.planned_at.tzinfo is None or payload.planned_at.utcoffset() is None:
                        raise LearningConflictError("planned_at must be timezone-aware")
                    session["planned_at"] = payload.planned_at.astimezone(UTC).isoformat()
                if payload.minutes is not None:
                    session["minutes"] = payload.minutes
                updated = deepcopy(session)
                return data
            raise LearningConflictError("Study session not found")

        with self._learning.plan_transaction(owner_id, project_id):
            self._learning.mutate(owner_id, project_id, apply)
        if updated is None:
            raise LearningServiceError("Study session update failed")
        return StudySession.model_validate(updated)

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
            if not plan:
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

            existing = StudyPlan.model_validate(plan)
            if payload.regenerate:
                completed_ids = {
                    session.id for session in existing.sessions if session.status == "completed"
                }
                completed_kinds = Counter(
                    (session.topic_id, session.activity)
                    for session in existing.sessions
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
                generated = StudyPlan.model_validate(
                    {
                        **existing.model_dump(mode="json"),
                        "goal": normalized_goal,
                        "exam_at": exam_at,
                        "daily_minutes": payload.daily_minutes,
                    }
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
    def _public_question(
        cls,
        question: dict[str, Any],
        *,
        saved_at: str | datetime | None = None,
    ) -> QuestionResponse:
        return QuestionResponse(
            id=question["id"],
            topic_id=question["topic_id"],
            prompt=question["prompt"],
            difficulty_level=question.get("difficulty_level", 2),
            citations=question.get("citations", []),
            sources=cls._question_sources(question),
            grounding=cls._question_grounding(question),
            learning_mode=question.get("learning_mode", LearningMode.CONCEPT),
            mode=question.get("mode", "fallback"),
            saved=saved_at is not None,
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
    ) -> QuestionResponse:
        self._require_project(owner_id, project_id)
        with self._learning.question_transaction(owner_id, project_id):
            current = self._learning.get(owner_id, project_id)
            progress = self._progress(current.data)
            history = progress.setdefault("question_history", {})
            requests = progress.setdefault("question_requests", {})
            if request_id and request_id in requests:
                replay = history.get(requests[request_id])
                if replay is not None:
                    return self._public_question(
                        replay,
                        saved_at=progress.get("saved_questions", {}).get(replay["id"]),
                    )
            if progress.get("pending_question") and not replace_pending:
                pending = progress["pending_question"]
                return self._public_question(
                    pending,
                    saved_at=progress.get("saved_questions", {}).get(pending["id"]),
                )
            review_topic_id: str | None = None
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
                review_topic_id = parsed_review.topic_id
                if topic_id is not None and topic_id != review_topic_id:
                    raise LearningConflictError("Review session topic does not match")
            if topic_id is not None and topic_id not in progress["topics"]:
                raise LearningConflictError("Unknown practice topic")
            selected_topic_id = (
                review_topic_id
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
                    mastery=mastery,
                    difficulty_level=selected_difficulty,
                    learning_mode=learning_mode,
                )
            else:
                generated = fallback_question(
                    topic_id=selected_topic_id,
                    topic_name=topic["name"],
                    difficulty_level=selected_difficulty,
                    sources=[],
                    learning_mode=learning_mode,
                )
            proposed = {
                "topic_id": selected_topic_id,
                "prompt": generated.prompt,
                "expected_answer": generated.expected_answer,
                "difficulty_level": generated.difficulty_level,
                "learning_mode": generated.learning_mode.value,
                "citations": generated.citations,
                "grounding": generated.grounding.value,
                "mode": generated.mode,
                "grading": generated.model_dump(mode="json"),
                "review_session_id": review_session_id,
            }
            selected: dict[str, Any] | None = None

            def store_once(data: dict[str, Any]) -> dict[str, Any]:
                nonlocal selected
                inner_progress = self._progress(data)
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

            self._learning.mutate(owner_id, project_id, store_once)
            if selected is None:
                raise LearningServiceError("Question generation failed")
            return self._public_question(selected)

    def pending_question(self, owner_id: str, project_id: str) -> QuestionResponse:
        self._require_project(owner_id, project_id)
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
            selected = deepcopy(stored_question)
            selected.pop("review_session_id", None)
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
    ) -> AnswerResponse:
        self._require_project(owner_id, project_id)
        current = self._learning.get(owner_id, project_id)
        if payload.attempt_id in current.data["attempts"]:
            stored_attempt = current.data["attempts"][payload.attempt_id]
            stored_grounding = stored_attempt.get("grounding") or (
                Grounding.MATERIAL.value
                if stored_attempt.get("sources")
                else Grounding.GENERAL.value
            )
            return AnswerResponse.model_validate(
                {**stored_attempt, "grounding": stored_grounding, "replayed": True}
            )
        current_progress = self._progress(current.data)
        current_question = current_progress.get("pending_question")
        if current_question is None or current_question["id"] != payload.question_id:
            raise LearningConflictError("Question is not pending")
        if "grading" in current_question:
            generated = GeneratedQuestion.model_validate(current_question["grading"])
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

        def grade_once(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal completed_review_session_id, next_review_at, replayed, result
            progress = self._progress(data)
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
            bkt_state = (
                update_bkt(current_bkt, is_correct=is_correct)
                if grade.mastery_evidence
                else current_bkt
            )
            difficulty = (
                update_difficulty(
                    current_difficulty,
                    is_correct=is_correct,
                    question_id=payload.question_id,
                )
                if grade.mastery_evidence
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
                    "mastery_updated": grade.mastery_evidence,
                },
            )
            raw_plan = progress.get("plan")
            if raw_plan:
                review_session_id = question.get("review_session_id")
                if review_session_id is not None:
                    review_session = next(
                        (
                            session
                            for session in raw_plan["sessions"]
                            if session.get("id") == review_session_id
                        ),
                        None,
                    )
                    if review_session is None:
                        raise LearningConflictError("Review session not found")
                    review_session["status"] = "completed"
                    completed_review_session_id = review_session_id
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
                    if not any(item["id"] == review_session.id for item in raw_plan["sessions"]):
                        raw_plan["sessions"].append(review_session.model_dump(mode="json"))
                        raw_plan["sessions"].sort(key=lambda item: item["planned_at"])
                    next_review_at = review_session.planned_at

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
                "mastery_updated": grade.mastery_evidence,
                "next_review_at": (
                    next_review_at.isoformat() if next_review_at is not None else None
                ),
                "answer": payload.answer,
                "observed_at": observed_at.isoformat(),
                "completed_review_session_id": completed_review_session_id,
                "question_snapshot": deepcopy(question),
            }
            data["attempts"][payload.attempt_id] = deepcopy(result)
            progress["bkt_states"][topic_id] = bkt_state.model_dump(mode="json")
            progress["difficulty_states"][topic_id] = difficulty.model_dump(mode="json")
            progress["evidence"].append(evidence.model_dump(mode="json"))
            progress["pending_question"] = None
            return data

        with self._learning.plan_transaction(owner_id, project_id):
            self._learning.mutate(owner_id, project_id, grade_once)
        if result is None:
            raise LearningServiceError("Answer grading failed")
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

    def evidence(self, owner_id: str, project_id: str) -> list[LearningEvidence]:
        self._require_project(owner_id, project_id)
        progress = self._progress(self._learning.get(owner_id, project_id).data)
        return [LearningEvidence.model_validate(item) for item in progress["evidence"]]
