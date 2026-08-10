"""Application service behind the five public MCP tools."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from hashlib import sha256
from threading import RLock
from time import monotonic, sleep
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select

from refineq.database.schema import material_chunks
from refineq.knowledge.index import KnowledgeIndex
from refineq.learning.bkt import DEFAULT_BKT
from refineq.learning.service import (
    AnswerRequest,
    LearningConflictError,
    LearningService,
    MaterialGroundingRequiredError,
)
from refineq.mcp.contracts import (
    BeginDemoInput,
    BeginDemoOutput,
    LearningContextOutput,
    MaterialSearchOutput,
    PracticeTaskInput,
    PracticeTaskOutput,
    RunInput,
    SearchMaterialsInput,
    SubmitAnswerInput,
    SubmitAnswerOutput,
)
from refineq.mcp.errors import McpServiceError
from refineq.mcp.observability import McpTelemetry
from refineq.mcp.projections import learning_context_projection, material_search_projection
from refineq.mcp.sandbox import (
    EVALUATION_LOGICAL_NOW,
    DemoBusyError,
    DemoRun,
    EvaluationSandboxService,
    IdempotencyConflictError,
    McpSandboxRepository,
    RunCompletedError,
    RunExpiredError,
    RunNotFoundError,
)
from refineq.storage.learning import LearningRepository
from refineq.storage.workspaces import WorkspaceRepository


class McpToolService:
    _idempotency_locks = tuple(RLock() for _ in range(256))

    def __init__(
        self,
        *,
        runs: McpSandboxRepository,
        sandbox: EvaluationSandboxService,
        workspaces: WorkspaceRepository,
        learning: LearningRepository,
        learning_service: LearningService,
        knowledge: KnowledgeIndex,
        account_email: str,
        telemetry: McpTelemetry | None = None,
        model_settings: Any | None = None,
    ) -> None:
        self._runs = runs
        self._sandbox = sandbox
        self._workspaces = workspaces
        self._learning = learning
        self._learning_service = learning_service
        self._knowledge = knowledge
        self._account_email = account_email
        self._telemetry = telemetry
        self._model_settings = model_settings

    @classmethod
    def _idempotency_lock(cls, run_id: str, tool_name: str, key: str) -> RLock:
        digest = sha256(f"{run_id}:{tool_name}:{key}".encode()).digest()
        return cls._idempotency_locks[int.from_bytes(digest[:2]) % len(cls._idempotency_locks)]

    @staticmethod
    def _validate(model: Any, payload: dict[str, Any]):
        try:
            return model.model_validate(payload)
        except ValidationError as error:
            raise McpServiceError(
                "invalid_input",
                "The tool input is invalid.",
                next_action="Correct the input using the published schema.",
            ) from error

    @staticmethod
    def _bounded_feedback(items: list[str]) -> list[str]:
        return [str(item)[:300] for item in items[:5]]

    def _active_state(self, run_id: str):
        run = self._runs.require_active(run_id)
        state = self._sandbox.state(expected_run_fence=run.run_fence)
        return run, state

    def _scope_guard(self, run: DemoRun) -> None:
        self._sandbox.state(expected_run_fence=run.run_fence)
        self._runs.require_active(run.run_token)

    @staticmethod
    def _translate(error: Exception) -> McpServiceError:
        if isinstance(error, DemoBusyError):
            return McpServiceError(
                "demo_busy",
                "Another evaluation run is active; retry shortly.",
                retryable=True,
                retry_after_ms=1_000,
                next_action="Retry refineq_begin_demo with the same client_run_key.",
            )
        if isinstance(error, RunExpiredError):
            return McpServiceError(
                "run_expired",
                "The evaluation run has expired.",
                retryable=True,
                next_action="Call refineq_begin_demo with a new client_run_key.",
            )
        if isinstance(error, RunCompletedError):
            return McpServiceError(
                "run_completed",
                "The evaluation run is already complete.",
                next_action="Call refineq_begin_demo with a new client_run_key.",
            )
        if isinstance(error, RunNotFoundError):
            return McpServiceError(
                "run_not_found",
                "The evaluation run was not found.",
                next_action="Call refineq_begin_demo first.",
            )
        if isinstance(error, IdempotencyConflictError):
            return McpServiceError(
                "idempotency_conflict",
                "The idempotency key was already used with different input.",
                next_action="Reuse the original input or choose a new idempotency key.",
            )
        if isinstance(error, MaterialGroundingRequiredError):
            return McpServiceError(
                "material_required",
                "The required evaluation material is unavailable.",
                next_action="Ask the operator to repair the evaluation seed.",
            )
        if isinstance(error, LearningConflictError):
            return McpServiceError(
                "state_conflict",
                "The learning state changed; read the context and retry.",
                retryable=True,
                next_action="Call refineq_get_learning_context.",
            )
        return McpServiceError(
            "internal_error",
            "The request could not be completed.",
            retryable=True,
        )

    def begin_demo(self, *, client_run_key: str) -> BeginDemoOutput:
        payload = self._validate(BeginDemoInput, {"client_run_key": client_run_key})
        observed_at = datetime.now(UTC)
        try:
            run = self._runs.begin(payload.client_run_key, now=observed_at)
            if run.status == "seeding" and run.replayed:
                if self._telemetry is not None:
                    self._telemetry.record_event("idempotency_replay")
                deadline = monotonic() + 5.0
                while run.status == "seeding" and monotonic() < deadline:
                    sleep(0.02)
                    run = self._runs.begin(payload.client_run_key)
                if run.status == "seeding":
                    raise DemoBusyError("The evaluation sandbox is still initializing")
            if not run.replayed:
                try:
                    state = self._sandbox.reset(
                        now=observed_at,
                        run_fence=run.run_fence,
                        scope_guard=lambda: self._runs.require_seeding(run.run_token),
                    )
                    self._runs.activate(run.run_token)
                except Exception as error:
                    self._runs.fail(
                        run.run_token,
                        error_code="sandbox_reset_failed",
                    )
                    raise McpServiceError(
                        "demo_seed_failed",
                        "The evaluation sandbox could not be reset.",
                        retryable=True,
                        next_action="Retry refineq_begin_demo with the same client_run_key.",
                    ) from error
            else:
                state = self._sandbox.state(expected_run_fence=run.run_fence)
        except McpServiceError:
            raise
        except Exception as error:
            raise self._translate(error) from error
        retrieval_mode = self._retrieval_mode(state)
        model_configured = False
        if self._model_settings is not None:
            try:
                model_configured = bool(self._model_settings.public(state.owner_id).configured)
            except Exception:
                model_configured = False
        return BeginDemoOutput(
            run_id=run.run_token,
            expires_at=run.expires_at.isoformat(),
            simulation=True,
            account={"email": self._account_email},
            space={
                "id": state.workspace_id,
                "title": "Function Limits Evaluation",
                "material_count": 1,
                "seed_version": run.seed_version,
            },
            runtime={
                "question": {
                    "configured": model_configured,
                    "mode": "ai" if model_configured else "deterministic_fallback",
                },
                "grading": {
                    "configured": model_configured,
                    "mode": "ai" if model_configured else "deterministic_fallback",
                },
                "retrieval": {
                    "configured": retrieval_mode == "hybrid",
                    "mode": retrieval_mode,
                },
                "observed_at": None,
                "stale": True,
            },
            next_tool="refineq_get_learning_context",
        )

    def _retrieval_mode(self, state) -> str:
        with self._knowledge.database.session() as session:
            embedded = session.scalar(
                select(func.count())
                .select_from(material_chunks)
                .where(
                    material_chunks.c.owner_id == state.owner_id,
                    material_chunks.c.project_id == "library",
                    material_chunks.c.material_id == state.material_id,
                    material_chunks.c.embedding.is_not(None),
                )
            )
        return "hybrid" if embedded else "lexical"

    def get_learning_context(self, *, run_id: str) -> LearningContextOutput:
        payload = self._validate(RunInput, {"run_id": run_id})
        try:
            run, state = self._active_state(payload.run_id)
            projection = learning_context_projection(
                owner_id=state.owner_id,
                workspace_id=state.workspace_id,
                workspaces=self._workspaces,
                learning=self._learning,
                knowledge=self._knowledge,
                now=EVALUATION_LOGICAL_NOW,
            )
            pending = projection.get("pending_question")
            if pending is not None:
                pending["id"] = self._runs.public_question_id(
                    payload.run_id,
                    str(pending["id"]),
                )
            self._scope_guard(run)
        except Exception as error:
            raise self._translate(error) from error
        return LearningContextOutput(
            run_id=payload.run_id,
            simulation=True,
            **projection,
        )

    def search_materials(
        self,
        *,
        run_id: str,
        query: str,
        limit: int = 5,
    ) -> MaterialSearchOutput:
        payload = self._validate(
            SearchMaterialsInput,
            {"run_id": run_id, "query": query, "limit": limit},
        )
        try:
            run, state = self._active_state(payload.run_id)
            projection = material_search_projection(
                owner_id=state.owner_id,
                workspace_id=state.workspace_id,
                query=payload.query,
                limit=payload.limit,
                knowledge=self._knowledge,
            )
            retrieval_mode = projection.pop("retrieval_mode")
            self._scope_guard(run)
        except Exception as error:
            raise self._translate(error) from error
        return MaterialSearchOutput(
            run_id=payload.run_id,
            query=payload.query,
            retrieval_mode=retrieval_mode,
            **projection,
        )

    def get_practice_task(
        self,
        *,
        run_id: str,
        request_id: str,
        topic_id: str | None = None,
        difficulty: int = 3,
    ) -> PracticeTaskOutput:
        payload = self._validate(
            PracticeTaskInput,
            {
                "run_id": run_id,
                "request_id": request_id,
                "topic_id": topic_id,
                "difficulty": difficulty,
            },
        )
        input_payload = payload.model_dump(mode="json", exclude={"run_id", "request_id"})
        with self._idempotency_lock(
            payload.run_id,
            "refineq_get_practice_task",
            payload.request_id,
        ):
            return self._get_practice_task_locked(payload, input_payload)

    def _get_practice_task_locked(
        self,
        payload: PracticeTaskInput,
        input_payload: dict[str, Any],
    ) -> PracticeTaskOutput:
        try:
            run, state = self._active_state(payload.run_id)
            replay = self._runs.get_idempotency(
                payload.run_id,
                tool_name="refineq_get_practice_task",
                key=payload.request_id,
                input_payload=input_payload,
            )
            if replay is not None:
                if self._telemetry is not None:
                    self._telemetry.record_event("idempotency_replay")
                return PracticeTaskOutput.model_validate(
                    {
                        "run_id": payload.run_id,
                        **replay,
                        "request_id": payload.request_id,
                    }
                )
            claimed = self._runs.claim_idempotency(
                payload.run_id,
                tool_name="refineq_get_practice_task",
                key=payload.request_id,
                input_payload=input_payload,
            )
            if claimed is not None:
                return PracticeTaskOutput.model_validate(
                    {
                        "run_id": payload.run_id,
                        **claimed,
                        "request_id": payload.request_id,
                    }
                )
            domain_request_id = self._runs.domain_idempotency_id(
                payload.run_id,
                "refineq_get_practice_task",
                payload.request_id,
            )
            question = self._learning_service.next_question(
                state.owner_id,
                state.workspace_id,
                topic_id=payload.topic_id or state.topic_id,
                difficulty_level=payload.difficulty,
                request_id=domain_request_id,
                require_material_grounding=True,
                expected_scope_fence=run.run_fence,
                scope_guard=lambda: self._scope_guard(run),
            )
            record = self._learning.get(state.owner_id, state.workspace_id)
            result = PracticeTaskOutput(
                run_id=payload.run_id,
                request_id=payload.request_id,
                question_id=self._runs.public_question_id(payload.run_id, question.id),
                topic_id=question.topic_id,
                prompt=question.prompt,
                difficulty=question.difficulty_level,
                citations=question.citations,
                grounding="material",
                mode=question.mode,
                state_version=record.version,
                simulation=True,
            )
            self._scope_guard(run)
            self._runs.save_idempotency(
                payload.run_id,
                tool_name="refineq_get_practice_task",
                key=payload.request_id,
                input_payload=input_payload,
                result=result.model_dump(
                    mode="json",
                    exclude_none=True,
                    exclude={"run_id", "request_id"},
                ),
            )
            canonical = self._runs.get_idempotency(
                payload.run_id,
                tool_name="refineq_get_practice_task",
                key=payload.request_id,
                input_payload=input_payload,
            )
            self._scope_guard(run)
            return PracticeTaskOutput.model_validate(
                {
                    "run_id": payload.run_id,
                    **(canonical or {}),
                    "request_id": payload.request_id,
                }
            )
        except Exception as error:
            raise self._translate(error) from error

    def submit_answer(
        self,
        *,
        run_id: str,
        question_id: str,
        answer: str,
        attempt_id: str,
        expected_state_version: int,
    ) -> SubmitAnswerOutput:
        payload = self._validate(
            SubmitAnswerInput,
            {
                "run_id": run_id,
                "question_id": question_id,
                "answer": answer,
                "attempt_id": attempt_id,
                "expected_state_version": expected_state_version,
            },
        )
        input_payload = payload.model_dump(mode="json", exclude={"run_id", "attempt_id"})
        with self._idempotency_lock(
            payload.run_id,
            "refineq_submit_answer",
            payload.attempt_id,
        ):
            return self._submit_answer_locked(payload, input_payload)

    def _submit_answer_locked(
        self,
        payload: SubmitAnswerInput,
        input_payload: dict[str, Any],
    ) -> SubmitAnswerOutput:
        try:
            replay = self._runs.get_idempotency(
                payload.run_id,
                tool_name="refineq_submit_answer",
                key=payload.attempt_id,
                input_payload=input_payload,
            )
            if replay is not None:
                if self._telemetry is not None:
                    self._telemetry.record_event("idempotency_replay")
                self._runs.complete(payload.run_id)
                return SubmitAnswerOutput.model_validate(
                    {
                        "run_id": payload.run_id,
                        **replay,
                        "attempt_id": payload.attempt_id,
                    }
                )
            run, state = self._active_state(payload.run_id)
            claimed = self._runs.claim_idempotency(
                payload.run_id,
                tool_name="refineq_submit_answer",
                key=payload.attempt_id,
                input_payload=input_payload,
            )
            if claimed is not None:
                self._runs.complete(payload.run_id)
                return SubmitAnswerOutput.model_validate(
                    {
                        "run_id": payload.run_id,
                        **claimed,
                        "attempt_id": payload.attempt_id,
                    }
                )
            domain_attempt_id = self._runs.domain_idempotency_id(
                payload.run_id,
                "refineq_submit_answer",
                payload.attempt_id,
            )
            before = self._learning.get(state.owner_id, state.workspace_id)
            stored_attempt = before.data["attempts"].get(domain_attempt_id)
            if stored_attempt is None:
                if before.version != payload.expected_state_version:
                    raise LearningConflictError("Learning state version changed")
                pending = before.data["progress"].get("pending_question")
                if pending is None:
                    raise LearningConflictError("Question is not pending")
                domain_question_id = str(pending["id"])
                public_question_id = self._runs.public_question_id(
                    payload.run_id,
                    domain_question_id,
                )
                if not hmac.compare_digest(public_question_id, payload.question_id):
                    raise LearningConflictError("Question belongs to a different run")
                before_mastery = float(
                    before.data["progress"]["bkt_states"][state.topic_id]["p_mastery"]
                )
            else:
                domain_question_id = str(stored_attempt["question_id"])
                public_question_id = self._runs.public_question_id(
                    payload.run_id,
                    domain_question_id,
                )
                question_matches = hmac.compare_digest(
                    public_question_id,
                    payload.question_id,
                )
                answer_matches = hmac.compare_digest(
                    str(stored_attempt.get("answer") or ""),
                    payload.answer,
                )
                if not question_matches or not answer_matches:
                    raise IdempotencyConflictError(
                        "The domain attempt belongs to different submit input"
                    )
                after_value = float(
                    before.data["progress"]["bkt_states"][state.topic_id]["p_mastery"]
                )
                before_mastery = (
                    DEFAULT_BKT.p_mastery if stored_attempt.get("mastery_updated") else after_value
                )
            graded = self._learning_service.submit_answer(
                state.owner_id,
                state.workspace_id,
                AnswerRequest(
                    attempt_id=domain_attempt_id,
                    question_id=domain_question_id,
                    answer=payload.answer,
                ),
                require_material_grounding=True,
                expected_scope_fence=run.run_fence,
                scope_guard=lambda: self._scope_guard(run),
            )
            self._scope_guard(run)
            after = self._learning.get(state.owner_id, state.workspace_id)
            after_mastery = float(after.data["progress"]["bkt_states"][state.topic_id]["p_mastery"])
            result = SubmitAnswerOutput(
                run_id=payload.run_id,
                attempt_id=payload.attempt_id,
                question_id=public_question_id,
                score=graded.score,
                passed=graded.is_correct,
                strengths=self._bounded_feedback(graded.strengths),
                gaps=self._bounded_feedback(graded.gaps),
                misconceptions=self._bounded_feedback(graded.misconceptions),
                citations=graded.citations[:8],
                grading_mode=graded.grading_mode,
                evidence_source="mcp_relayed",
                simulation=True,
                mastery_effect={
                    "applied_to_sandbox": True,
                    "applied_to_real_learner": False,
                    "topic_id": graded.topic_id,
                    "before": round(before_mastery, 4),
                    "after": round(after_mastery, 4),
                    "changed": after_mastery != before_mastery,
                    "updated": graded.mastery_updated,
                },
                final_state={"status": "completed", "state_version": after.version},
                next_action={
                    "tool": "refineq_begin_demo",
                    "reason": "Use a new client_run_key to start another simulation.",
                },
            )
            self._runs.save_idempotency(
                payload.run_id,
                tool_name="refineq_submit_answer",
                key=payload.attempt_id,
                input_payload=input_payload,
                result=result.model_dump(
                    mode="json",
                    exclude_none=True,
                    exclude={"run_id", "attempt_id"},
                ),
            )
            self._runs.complete(payload.run_id)
            canonical = self._runs.get_idempotency(
                payload.run_id,
                tool_name="refineq_submit_answer",
                key=payload.attempt_id,
                input_payload=input_payload,
            )
            return SubmitAnswerOutput.model_validate(
                {
                    "run_id": payload.run_id,
                    **(canonical or {}),
                    "attempt_id": payload.attempt_id,
                }
            )
        except McpServiceError:
            raise
        except Exception as error:
            raise self._translate(error) from error
