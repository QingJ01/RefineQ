"""Application service for the deterministic learning journey."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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
    KnowledgeType,
    LearningEvidence,
    StudyPlan,
)
from refineq.learning.planning import build_study_plan
from refineq.storage.json_store import RecordNotFoundError
from refineq.storage.learning import LearningRepository
from refineq.storage.projects import ProjectRepository


class LearningServiceError(RuntimeError):
    code = "learning_error"


class ProjectNotFoundError(LearningServiceError):
    code = "project_not_found"


class LearningNotSeededError(LearningServiceError):
    code = "learning_not_seeded"


class LearningConflictError(LearningServiceError):
    code = "learning_conflict"


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
    mode: str = "fallback"


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
    grading_mode: str = "fallback"
    replayed: bool = False


class ProgressResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str
    goal: str
    mastery: dict[str, float]
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
                "topics": {
                    topic.id: topic.model_dump(mode="json") for topic in payload.topics
                },
                "bkt_states": {
                    topic.id: DEFAULT_BKT.model_dump(mode="json") for topic in payload.topics
                },
                "difficulty_states": {
                    topic.id: DifficultyState().model_dump(mode="json")
                    for topic in payload.topics
                },
                "diagnostic_runs": [],
                "evidence": [],
                "pending_question": None,
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
                evidence = create_evidence(
                    kind="diagnostic",
                    source_id=f"{project_id}:{payload.diagnostic_id}:{result.topic_id}",
                    summary=(
                        f"Diagnostic response for {result.topic_id} was "
                        f"{'correct' if result.is_correct else 'incorrect'}."
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

    @staticmethod
    def _public_question(question: dict[str, Any]) -> QuestionResponse:
        return QuestionResponse(
            id=question["id"],
            topic_id=question["topic_id"],
            prompt=question["prompt"],
            difficulty_level=question.get("difficulty_level", 2),
            citations=question.get("citations", []),
            mode=question.get("mode", "fallback"),
        )

    def next_question(self, owner_id: str, project_id: str) -> QuestionResponse:
        self._require_project(owner_id, project_id)
        current = self._learning.get(owner_id, project_id)
        progress = self._progress(current.data)
        if progress.get("pending_question"):
            return self._public_question(progress["pending_question"])
        topic_id = min(
            progress["topics"],
            key=lambda candidate: (
                BKTState.model_validate(progress["bkt_states"][candidate]).p_mastery,
                candidate,
            ),
        )
        topic = progress["topics"][topic_id]
        mastery = BKTState.model_validate(progress["bkt_states"][topic_id]).p_mastery
        difficulty_level = DifficultyState.model_validate(
            progress["difficulty_states"][topic_id]
        ).level
        if self._intelligence is not None:
            generated = self._intelligence.generate_question(
                owner_id=owner_id,
                workspace_id=project_id,
                topic_id=topic_id,
                topic_name=topic["name"],
                mastery=mastery,
                difficulty_level=difficulty_level,
            )
        else:
            generated = fallback_question(
                topic_id=topic_id,
                topic_name=topic["name"],
                difficulty_level=difficulty_level,
                sources=[],
            )
        question_id = stable_id(
            "question",
            project_id,
            topic_id,
            str(len(current.data["attempts"])),
        )
        proposed = {
            "id": question_id,
            "topic_id": topic_id,
            "prompt": generated.prompt,
            "expected_answer": generated.expected_answer,
            "difficulty_level": generated.difficulty_level,
            "citations": generated.citations,
            "mode": generated.mode,
            "grading": generated.model_dump(mode="json"),
        }
        selected: dict[str, Any] | None = None

        def store_once(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal selected
            inner_progress = self._progress(data)
            selected = inner_progress.get("pending_question") or proposed
            inner_progress["pending_question"] = selected
            return data

        self._learning.mutate(owner_id, project_id, store_once)
        if selected is None:
            raise LearningServiceError("Question generation failed")
        return self._public_question(selected)

    def submit_answer(
        self,
        owner_id: str,
        project_id: str,
        payload: AnswerRequest,
    ) -> AnswerResponse:
        self._require_project(owner_id, project_id)
        current = self._learning.get(owner_id, project_id)
        if payload.attempt_id in current.data["attempts"]:
            return AnswerResponse.model_validate(
                {**current.data["attempts"][payload.attempt_id], "replayed": True}
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
            expected = current_question["expected_answer"].strip().casefold()
            matched = expected in payload.answer.strip().casefold()
            generated = fallback_question(
                topic_id=current_question["topic_id"],
                topic_name=current_question["expected_answer"],
                difficulty_level=2,
                sources=[],
            )
            grade = fallback_grade(generated, payload.answer)
            if matched and not grade.passed:
                grade = grade.model_copy(update={"score": 100, "passed": True})
        result: dict[str, Any] | None = None
        replayed = False

        def grade_once(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal replayed, result
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
            bkt_state = update_bkt(
                BKTState.model_validate(progress["bkt_states"][topic_id]),
                is_correct=is_correct,
            )
            difficulty = update_difficulty(
                DifficultyState.model_validate(progress["difficulty_states"][topic_id]),
                is_correct=is_correct,
                question_id=payload.question_id,
            )
            evidence = create_evidence(
                kind="attempt",
                source_id=payload.attempt_id,
                summary=(
                    f"Practice response for {topic_id} was "
                    f"{'correct' if is_correct else 'incorrect'}."
                ),
                observed_at=datetime.now(UTC),
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
                },
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
                "grading_mode": grade.mode,
            }
            data["attempts"][payload.attempt_id] = deepcopy(result)
            progress["bkt_states"][topic_id] = bkt_state.model_dump(mode="json")
            progress["difficulty_states"][topic_id] = difficulty.model_dump(mode="json")
            progress["evidence"].append(evidence.model_dump(mode="json"))
            progress["pending_question"] = None
            return data

        self._learning.mutate(owner_id, project_id, grade_once)
        if result is None:
            raise LearningServiceError("Answer grading failed")
        return AnswerResponse.model_validate({**result, "replayed": replayed})

    def progress(self, owner_id: str, project_id: str) -> ProgressResponse:
        self._require_project(owner_id, project_id)
        return self._progress_response(self._learning.get(owner_id, project_id).data)

    def evidence(self, owner_id: str, project_id: str) -> list[LearningEvidence]:
        self._require_project(owner_id, project_id)
        progress = self._progress(self._learning.get(owner_id, project_id).data)
        return [LearningEvidence.model_validate(item) for item in progress["evidence"]]
