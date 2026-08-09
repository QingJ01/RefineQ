"""Home supervisor orchestration with deterministic boundaries and safe writes."""

from __future__ import annotations

import re
from contextlib import suppress
from datetime import UTC, date, datetime, time, timedelta, timezone
from hashlib import sha256
from time import perf_counter

from openai import OpenAIError
from pydantic import ValidationError

from refineq.agent.settings import ModelNotConfiguredError
from refineq.agent.structured import StructuredModelResponseError
from refineq.home.events import (
    HomeDispatchEvent,
    HomeEventRepository,
    HomeReceiptRepository,
    latency_bucket,
    request_id_hash,
)
from refineq.home.intelligence import HomeIntelligence
from refineq.home.models import (
    Clarification,
    ClarificationOption,
    HomeActionReceipt,
    HomeConfirmRequest,
    HomeDispatchRequest,
    HomeDispatchResult,
    WorkspaceActionProposal,
    WorkspaceDispatchSummary,
    WorkspaceProposal,
    WorkspaceTarget,
)
from refineq.home.policy import (
    HomeRoutingPolicy,
    PolicyDecision,
    PolicyKind,
    select_dispatch_candidates,
)
from refineq.home.tokens import HomeTokenError, HomeTokenSigner, proposal_hash
from refineq.knowledge.index import KnowledgeIndex
from refineq.learning.models import BKTState, StudyPlan
from refineq.learning.next_action import select_next_action
from refineq.learning.service import LearningService, PlanSessionUpdate
from refineq.storage.learning import LearningRepository
from refineq.workspaces.constraints import infer_intent_constraints
from refineq.workspaces.models import LearningWorkspace, WorkspaceRoutingDecision
from refineq.workspaces.service import (
    DEFAULT_CAPABILITY_HORIZON_DAYS,
    WorkspaceConflictError,
    WorkspaceResolutionPreview,
    WorkspaceResolveRequest,
    WorkspaceService,
)


class HomeServiceError(RuntimeError):
    code = "home_dispatch_error"


class HomeConfirmationError(HomeServiceError):
    code = "invalid_home_confirmation"


class HomeActionConflictError(HomeServiceError):
    code = "home_action_conflict"


class HomeModelUnavailableError(HomeServiceError):
    code = "home_model_unavailable"


def _state_hash(workspaces: list[LearningWorkspace]) -> str:
    serialized = "|".join(
        item.model_dump_json() for item in sorted(workspaces, key=lambda value: value.id)
    )
    return sha256(serialized.encode()).hexdigest()


def _workspace_proposal_payload(proposal: WorkspaceProposal | dict) -> dict:
    value = proposal if isinstance(proposal, dict) else proposal.model_dump(mode="json")
    fields = (
        "proposal_type",
        "title",
        "goal",
        "subject",
        "topics",
        "keywords",
        "exam_at",
        "daily_minutes",
        "material_hint",
        "reason",
        "idempotency_key",
    )
    result = {field: value[field] for field in fields}
    raw_exam_at = result["exam_at"]
    if isinstance(raw_exam_at, datetime):
        parsed_exam_at = raw_exam_at
    else:
        parsed_exam_at = datetime.fromisoformat(str(raw_exam_at).replace("Z", "+00:00"))
    result["exam_at"] = parsed_exam_at.astimezone(UTC).isoformat()
    return result


def _action_proposal_payload(proposal: WorkspaceActionProposal | dict) -> dict:
    value = proposal if isinstance(proposal, dict) else proposal.model_dump(mode="json")
    fields = (
        "proposal_type",
        "action_type",
        "risk_level",
        "workspace_id",
        "workspace_title",
        "before",
        "after",
        "affected_refs",
        "idempotency_key",
    )
    return {field: value[field] for field in fields}


class HomeDispatchService:
    def __init__(
        self,
        *,
        workspace_service: WorkspaceService,
        learning: LearningRepository,
        learning_service: LearningService,
        knowledge: KnowledgeIndex,
        intelligence: HomeIntelligence,
        signer: HomeTokenSigner,
        events: HomeEventRepository,
        receipts: HomeReceiptRepository,
        policy: HomeRoutingPolicy | None = None,
    ) -> None:
        self._workspace_service = workspace_service
        self._learning = learning
        self._learning_service = learning_service
        self._knowledge = knowledge
        self._intelligence = intelligence
        self._signer = signer
        self._events = events
        self._receipts = receipts
        self._policy = policy or HomeRoutingPolicy()

    def load_dispatch_summaries(
        self,
        owner_id: str,
        workspaces: list[LearningWorkspace],
        *,
        now: datetime,
        timezone_offset_minutes: int,
    ) -> list[WorkspaceDispatchSummary]:
        """Assemble NextAction-compatible summaries from two batched owner reads."""

        workspace_ids = [item.id for item in workspaces]
        learning_records = self._learning.load_dispatch_records(owner_id, workspace_ids)
        material_counts = self._knowledge.material_status_counts_for_projects(
            owner_id=owner_id,
            project_ids=workspace_ids,
        )
        summaries: list[WorkspaceDispatchSummary] = []
        for workspace in workspaces:
            record = learning_records.get(workspace.id)
            if record is None:
                continue
            progress = record.data.get("progress") or {}
            raw_plan = progress.get("plan")
            plan = StudyPlan.model_validate(raw_plan) if raw_plan else None
            mastery = {
                topic_id: BKTState.model_validate(state).p_mastery
                for topic_id, state in (progress.get("bkt_states") or {}).items()
            }
            topic_names = {
                topic_id: str(topic.get("name") or topic_id)
                for topic_id, topic in (progress.get("topics") or {}).items()
            }
            statuses = [
                status
                for status, count in material_counts.get(workspace.id, {}).items()
                for _ in range(count)
            ]
            next_action = select_next_action(
                workspace_id=workspace.id,
                version=record.version,
                plan=plan,
                material_statuses=statuses,
                mastery=mastery,
                topic_names=topic_names,
                now=now,
                timezone_offset_minutes=timezone_offset_minutes,
            )
            summaries.append(
                WorkspaceDispatchSummary(
                    id=workspace.id,
                    title=workspace.title,
                    subject=workspace.subject,
                    goal=workspace.goal,
                    archived=workspace.archived,
                    last_active_at=workspace.last_active_at,
                    exam_at=plan.exam_at if plan else None,
                    next_action=next_action,
                    pace_risk=next_action.risk_level,
                )
            )
        return summaries

    @staticmethod
    def _rank_summary(summary: WorkspaceDispatchSummary, now: datetime) -> tuple:
        action = summary.next_action
        priority = {
            "start_review": 0,
            "start_session": 1,
            "repair_pace": 2,
            "start_practice": 4,
        }.get(action.action_type if action else "", 4)
        if action and action.action_type == "upload_material":
            soon = summary.exam_at is not None and summary.exam_at <= now + timedelta(days=7)
            priority = 3 if soon else 4
        exam_at = summary.exam_at or datetime.max.replace(tzinfo=UTC)
        risk = {"high": 0, "medium": 1, "low": 2}[summary.pace_risk]
        return (priority, exam_at, risk, -summary.last_active_at.timestamp(), summary.id)

    def dispatch(
        self,
        owner_id: str,
        payload: HomeDispatchRequest,
        *,
        is_admin: bool = False,
        now: datetime | None = None,
    ) -> HomeDispatchResult:
        started = perf_counter()
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        workspaces = self._workspace_service.list(owner_id, include_archived=True)
        candidates, truncated = select_dispatch_candidates(payload.text, workspaces)
        try:
            if payload.clarification is not None:
                result = self._dispatch_clarified(
                    owner_id,
                    payload,
                    candidates,
                    truncated=truncated,
                    is_admin=is_admin,
                    now=observed_at,
                )
            else:
                decision = self._policy.decide(payload.text, workspaces)
                result = self._dispatch_decision(
                    owner_id,
                    payload,
                    decision,
                    candidates,
                    truncated=truncated,
                    is_admin=is_admin,
                    now=observed_at,
                )
        except (OpenAIError, StructuredModelResponseError, ValidationError, TimeoutError):
            result = self._deterministic_model_fallback(
                owner_id,
                payload,
                candidates,
                truncated=truncated,
                now=observed_at,
            )
        elapsed_ms = max(0, int((perf_counter() - started) * 1_000))
        with suppress(Exception):
            self._events.record(
                owner_id,
                HomeDispatchEvent(
                    request_id_hash=request_id_hash(payload.request_id),
                    result_kind=result.kind,
                    decided_by=result.decided_by,
                    latency_bucket=latency_bucket(elapsed_ms),
                    latency_ms=elapsed_ms,
                    candidate_count=len(candidates),
                    occurred_at=observed_at,
                ),
            )
        return result

    def _dispatch_decision(
        self,
        owner_id: str,
        payload: HomeDispatchRequest,
        decision: PolicyDecision,
        candidates: list[LearningWorkspace],
        *,
        truncated: bool,
        is_admin: bool,
        now: datetime,
    ) -> HomeDispatchResult:
        if decision.kind == PolicyKind.EXPLICIT_WORKSPACE:
            return self._open_workspace_result(
                owner_id,
                payload,
                decision.workspace_ids[0],
                candidates,
                reason=decision.reason,
                explicit=True,
                truncated=truncated,
                now=now,
            )
        if decision.kind == PolicyKind.CROSS_WORKSPACE:
            return self._cross_workspace_result(
                owner_id, payload, candidates, truncated=truncated, now=now
            )
        if decision.kind == PolicyKind.WORKSPACE_ACTION:
            return self._workspace_action_result(
                owner_id, payload, candidates, decision=decision, now=now
            )
        if decision.kind == PolicyKind.STRONG_LONG_TERM:
            return self._long_term_result(
                owner_id, payload, strong=True, now=now
            )
        if decision.kind in {PolicyKind.AMBIGUOUS_LONG_TERM, PolicyKind.EVALUATION}:
            if decision.workspace_ids:
                return self._open_workspace_result(
                    owner_id,
                    payload,
                    decision.workspace_ids[0],
                    candidates,
                    reason=decision.reason,
                    explicit=False,
                    truncated=truncated,
                    now=now,
                )
            return self._long_term_result(owner_id, payload, strong=False, now=now)
        if decision.kind == PolicyKind.DIRECT_ANSWER:
            return self._direct_answer_result(
                owner_id, payload, reason=decision.reason, is_admin=is_admin, now=now
            )
        if decision.kind == PolicyKind.CLARIFY:
            return self._clarify_result(
                owner_id, payload, candidates, reason=decision.reason, now=now
            )
        if decision.kind == PolicyKind.OUT_OF_SCOPE:
            return self._out_of_scope_result(
                owner_id, payload, candidates, reason=decision.reason, now=now
            )

        summaries = self.load_dispatch_summaries(
            owner_id,
            candidates,
            now=now,
            timezone_offset_minutes=payload.timezone_offset_minutes,
        )
        try:
            semantic = self._intelligence.classify(owner_id, payload.text, summaries)
        except ModelNotConfiguredError:
            return self._model_unconfigured_result(
                owner_id, payload, summaries, is_admin=is_admin, now=now
            )
        if semantic.kind == "open_workspace" and semantic.workspace_id in {
            item.id for item in candidates
        }:
            return self._open_workspace_result(
                owner_id,
                payload,
                semantic.workspace_id,
                candidates,
                reason=semantic.reason,
                explicit=False,
                truncated=truncated,
                now=now,
                confidence=semantic.confidence,
                decided_by="model",
            )
        if semantic.kind == "direct_answer":
            return self._direct_answer_result(
                owner_id,
                payload,
                reason=semantic.reason,
                is_admin=is_admin,
                now=now,
                confidence=semantic.confidence,
            )
        if semantic.kind == "propose_workspace":
            return self._long_term_result(owner_id, payload, strong=False, now=now)
        if semantic.kind == "out_of_scope":
            return self._out_of_scope_result(
                owner_id, payload, candidates, reason=semantic.reason, now=now
            )
        return self._clarify_result(
            owner_id, payload, candidates, reason=semantic.reason, now=now
        )

    def _dispatch_clarified(
        self,
        owner_id: str,
        payload: HomeDispatchRequest,
        candidates: list[LearningWorkspace],
        *,
        truncated: bool,
        is_admin: bool,
        now: datetime,
    ) -> HomeDispatchResult:
        selection = payload.clarification
        if selection is None:
            raise HomeConfirmationError("Clarification selection is required")
        try:
            claims = self._signer.verify(
                selection.continuation_token,
                owner_id=owner_id,
                operation="clarify",
                now=now,
            )
        except HomeTokenError as error:
            raise HomeConfirmationError(str(error)) from error
        expected = proposal_hash({"text_hash": sha256(payload.text.encode()).hexdigest()})
        if claims.proposal_hash != expected:
            raise HomeConfirmationError("Clarification does not match this request")
        current_state = _state_hash(self._workspace_service.list(owner_id, include_archived=True))
        if claims.state_hash != current_state:
            return self._clarify_result(
                owner_id,
                payload,
                candidates,
                reason="学习空间列表已经变化，请重新选择。",
                now=now,
            )
        if selection.option_id == "direct_answer":
            original = self._policy.decide(payload.text, self._workspace_service.list(owner_id))
            if original.kind == PolicyKind.OUT_OF_SCOPE:
                return self._out_of_scope_result(
                    owner_id,
                    payload,
                    candidates,
                    reason="即使声明为学习任务，实时、高风险或破坏性请求仍不能在主页处理。",
                    now=now,
                )
            return self._direct_answer_result(
                owner_id,
                payload,
                reason="用户明确选择把它作为一次性学习问题处理。",
                is_admin=is_admin,
                now=now,
            )
        if selection.option_id == "choose_workspace":
            return self._cross_workspace_result(
                owner_id, payload, candidates, truncated=truncated, now=now
            )
        if selection.option_id == "create_workspace":
            return self._long_term_result(owner_id, payload, strong=False, now=now)
        return self._clarify_result(
            owner_id, payload, candidates, reason="请选择一个可用选项。", now=now
        )

    def _direct_answer_result(
        self,
        owner_id: str,
        payload: HomeDispatchRequest,
        *,
        reason: str,
        is_admin: bool,
        now: datetime,
        confidence: float = 0.94,
    ) -> HomeDispatchResult:
        try:
            answer = self._intelligence.answer(owner_id, payload.text)
        except ModelNotConfiguredError:
            return self._model_unconfigured_result(
                owner_id, payload, [], is_admin=is_admin, now=now
            )
        return HomeDispatchResult(
            request_id=payload.request_id,
            kind="direct_answer",
            reason=reason,
            confidence=confidence,
            decided_by="hybrid",
            expires_at=now + timedelta(minutes=10),
            answer=answer,
            limitations=["未使用个人资料或外部实时来源"],
        )

    def _open_workspace_result(
        self,
        owner_id: str,
        payload: HomeDispatchRequest,
        workspace_id: str,
        candidates: list[LearningWorkspace],
        *,
        reason: str,
        explicit: bool,
        truncated: bool,
        now: datetime,
        confidence: float = 0.98,
        decided_by: str = "rule",
        route_action: str = "reused",
    ) -> HomeDispatchResult:
        target = next((item for item in candidates if item.id == workspace_id), None)
        if target is None:
            raise HomeActionConflictError("Selected workspace is no longer available")
        summaries = self.load_dispatch_summaries(
            owner_id,
            [target],
            now=now,
            timezone_offset_minutes=payload.timezone_offset_minutes,
        )
        next_action = summaries[0].next_action if summaries else None
        limitations = ["仅比较了最近活跃的 8 个学习空间"] if truncated else []
        return HomeDispatchResult(
            request_id=payload.request_id,
            kind="open_workspace",
            reason=reason,
            confidence=confidence,
            decided_by=decided_by,
            expires_at=now + timedelta(minutes=10),
            workspace_target=WorkspaceTarget(
                workspace_id=target.id,
                title=target.title,
                reason=reason,
                match_kind="explicit_command" if explicit else "semantic_match",
                auto_navigate=explicit,
                route_action=route_action,
                next_action=next_action,
            ),
            limitations=limitations,
        )

    def _cross_workspace_result(
        self,
        owner_id: str,
        payload: HomeDispatchRequest,
        candidates: list[LearningWorkspace],
        *,
        truncated: bool,
        now: datetime,
    ) -> HomeDispatchResult:
        if not candidates:
            return self._long_term_result(owner_id, payload, strong=False, now=now)
        summaries = self.load_dispatch_summaries(
            owner_id,
            candidates,
            now=now,
            timezone_offset_minutes=payload.timezone_offset_minutes,
        )
        if not summaries:
            return self._clarify_result(
                owner_id, payload, candidates, reason="暂无可比较的学习计划。", now=now
            )
        ordered = sorted(summaries, key=lambda item: self._rank_summary(item, now))
        chosen = ordered[0]
        deferred = ordered[1].title if len(ordered) > 1 else None
        reason = chosen.next_action.reason if chosen.next_action else "这是当前优先行动。"
        return HomeDispatchResult(
            request_id=payload.request_id,
            kind="open_workspace",
            reason=reason,
            confidence=1,
            decided_by="rule",
            expires_at=now + timedelta(minutes=10),
            workspace_target=WorkspaceTarget(
                workspace_id=chosen.id,
                title=chosen.title,
                reason=reason,
                match_kind="semantic_match",
                auto_navigate=False,
                route_action="reused",
                next_action=chosen.next_action,
                deferred_workspace_title=deferred,
            ),
            limitations=(
                ["仅比较了最近活跃的 8 个学习空间，可从下方查看全部空间"]
                if truncated
                else []
            ),
        )

    def _long_term_result(
        self,
        owner_id: str,
        payload: HomeDispatchRequest,
        *,
        strong: bool,
        now: datetime,
    ) -> HomeDispatchResult:
        intent = payload.text[:500]
        preview = self._workspace_service.preview_resolution(
            owner_id,
            WorkspaceResolveRequest(intent=intent),
            now=now,
        )
        if preview.decision.workspace_id is not None:
            candidates, truncated = select_dispatch_candidates(
                payload.text,
                self._workspace_service.list(owner_id),
            )
            return self._open_workspace_result(
                owner_id,
                payload,
                preview.decision.workspace_id,
                candidates,
                reason=preview.decision.reason,
                explicit=False,
                truncated=truncated,
                now=now,
                confidence=preview.decision.confidence,
                decided_by="hybrid",
                route_action=preview.decision.action,
            )
        if strong:
            route = self._workspace_service.commit_resolution(owner_id, preview)
            return self._open_workspace_result(
                owner_id,
                payload,
                route.workspace.id,
                [route.workspace],
                reason=route.reason,
                explicit=True,
                truncated=False,
                now=now,
                confidence=route.confidence,
                decided_by="rule",
                route_action=route.action,
            )
        return self._workspace_proposal_result(owner_id, payload, preview, now=now)

    def _workspace_proposal_result(
        self,
        owner_id: str,
        payload: HomeDispatchRequest,
        preview: WorkspaceResolutionPreview,
        *,
        now: datetime,
    ) -> HomeDispatchResult:
        inferred = infer_intent_constraints(payload.text[:2_000], now=now)
        exam_at = inferred.exam_at or now + timedelta(days=DEFAULT_CAPABILITY_HORIZON_DAYS)
        daily_minutes = inferred.daily_minutes or 45
        decision = preview.decision
        proposal_data = {
            "proposal_type": "create_workspace",
            "title": decision.title,
            "goal": payload.text[:500],
            "subject": decision.subject,
            "topics": decision.topics,
            "keywords": decision.keywords,
            "exam_at": exam_at.isoformat(),
            "daily_minutes": daily_minutes,
            "material_hint": "上传一份与目标主题相关的讲义、教材或笔记",
            "reason": "该目标需要跨天计划、资料约束和学习证据，不能作为一次性回答完成。",
            "idempotency_key": f"create-{request_id_hash(payload.request_id)}",
        }
        token, expires_at = self._signer.issue(
            owner_id=owner_id,
            operation="create_workspace",
            proposal=_workspace_proposal_payload(proposal_data),
            state_hash=preview.workspace_snapshot_hash,
            now=now,
        )
        proposal = WorkspaceProposal(
            **proposal_data,
            confirmation_token=token,
            expires_at=expires_at,
        )
        return HomeDispatchResult(
            request_id=payload.request_id,
            kind="propose_workspace",
            reason=proposal.reason,
            confidence=decision.confidence,
            decided_by="hybrid",
            expires_at=expires_at,
            workspace_proposal=proposal,
            limitations=["确认前不会创建空间或学习事件"],
        )

    def _workspace_action_result(
        self,
        owner_id: str,
        payload: HomeDispatchRequest,
        candidates: list[LearningWorkspace],
        *,
        decision: PolicyDecision,
        now: datetime,
    ) -> HomeDispatchResult:
        target = next(
            (item for item in candidates if item.id in decision.workspace_ids),
            candidates[0] if len(candidates) == 1 else None,
        )
        if target is None:
            return self._clarify_result(
                owner_id,
                payload,
                candidates,
                reason="请先选择要修改计划的学习空间。",
                now=now,
            )
        record = self._learning.get(owner_id, target.id)
        raw_plan = (record.data.get("progress") or {}).get("plan")
        plan = StudyPlan.model_validate(raw_plan) if raw_plan else None
        if plan is None:
            raise HomeActionConflictError("Selected workspace has no editable plan")
        planned = sorted(
            (item for item in plan.sessions if item.status == "planned"),
            key=lambda item: (item.planned_at, item.id),
        )
        session = next(
            (
                item
                for item in planned
                if str(item.topic_id).casefold() in payload.text.casefold()
            ),
            planned[0] if planned else None,
        )
        if session is None:
            raise HomeActionConflictError("No planned session is available to edit")
        before = session.model_dump(mode="json")
        duration = self._parse_duration(payload.text)
        planned_at = self._parse_planned_at(
            payload.text,
            current=session.planned_at,
            now=now,
            timezone_offset_minutes=payload.timezone_offset_minutes,
        )
        if planned_at is not None:
            action_type = "reschedule_session"
            after = {**before, "planned_at": planned_at.isoformat()}
        elif duration is not None:
            action_type = "adjust_session_minutes"
            after = {**before, "minutes": duration}
        else:
            return self._clarify_result(
                owner_id,
                payload,
                candidates,
                reason="请说明要改到哪一天，或调整为多少分钟。",
                now=now,
            )
        idempotency_key = f"action-{request_id_hash(payload.request_id)}"
        proposal_data = {
            "proposal_type": "workspace_action",
            "action_type": action_type,
            "risk_level": "medium",
            "workspace_id": target.id,
            "workspace_title": target.title,
            "before": before,
            "after": after,
            "affected_refs": [session.id],
            "idempotency_key": idempotency_key,
        }
        token, expires_at = self._signer.issue(
            owner_id=owner_id,
            operation=action_type,
            target=target.id,
            proposal=proposal_data,
            state_hash=str(record.version),
            now=now,
        )
        proposal = WorkspaceActionProposal(
            **proposal_data,
            confirmation_token=token,
            expires_at=expires_at,
        )
        return HomeDispatchResult(
            request_id=payload.request_id,
            kind="workspace_action",
            reason="这是中风险计划修改；确认后才会写入。",
            confidence=0.95,
            decided_by="hybrid",
            expires_at=expires_at,
            action_proposal=proposal,
            limitations=["仅修改所列会话，不会重排整个计划"],
        )

    @staticmethod
    def _parse_duration(text: str) -> int | None:
        match = re.search(r"(\d{1,3})\s*(分钟|小时|minutes?|hours?)", text, re.I)
        if not match:
            return None
        value = int(match.group(1))
        if match.group(2).casefold() in {"小时", "hour", "hours"}:
            value *= 60
        return value if 5 <= value <= 480 else None

    @staticmethod
    def _parse_planned_at(
        text: str,
        *,
        current: datetime,
        now: datetime,
        timezone_offset_minutes: int,
    ) -> datetime | None:
        local_tz = timezone(timedelta(minutes=timezone_offset_minutes))
        local_now = now.astimezone(local_tz)
        local_current = current.astimezone(local_tz)
        target_date: date | None = None
        if "明天" in text or re.search(r"\btomorrow\b", text, re.I):
            target_date = local_now.date() + timedelta(days=1)
        elif "后天" in text:
            target_date = local_now.date() + timedelta(days=2)
        else:
            weekdays = {
                "一": 0,
                "二": 1,
                "三": 2,
                "四": 3,
                "五": 4,
                "六": 5,
                "日": 6,
                "天": 6,
                "monday": 0,
                "tuesday": 1,
                "wednesday": 2,
                "thursday": 3,
                "friday": 4,
                "saturday": 5,
                "sunday": 6,
            }
            match = re.search(
                r"(?:周|星期)([一二三四五六日天])|\b(" + "|".join(weekdays.keys()) + r")\b",
                text,
                re.I,
            )
            if match:
                key = (match.group(1) or match.group(2)).casefold()
                days = (weekdays[key] - local_now.weekday()) % 7 or 7
                target_date = local_now.date() + timedelta(days=days)
        if target_date is None:
            return None
        local_target = datetime.combine(
            target_date,
            time(local_current.hour, local_current.minute),
            tzinfo=local_tz,
        )
        return local_target.astimezone(UTC)

    def _clarify_result(
        self,
        owner_id: str,
        payload: HomeDispatchRequest,
        candidates: list[LearningWorkspace],
        *,
        reason: str,
        now: datetime,
    ) -> HomeDispatchResult:
        token, expires_at = self._signer.issue(
            owner_id=owner_id,
            operation="clarify",
            proposal={"text_hash": sha256(payload.text.encode()).hexdigest()},
            state_hash=_state_hash(self._workspace_service.list(owner_id, include_archived=True)),
            now=now,
        )
        options = [
            ClarificationOption(id="direct_answer", label="直接解释这一次"),
            ClarificationOption(id="create_workspace", label="作为长期目标新建空间"),
        ]
        if candidates:
            options.insert(1, ClarificationOption(id="choose_workspace", label="选择已有学习空间"))
        clarification = Clarification(
            question="你想快速了解这一次，还是把它作为持续学习任务？",
            options=options[:3],
            continuation_token=token,
        )
        return HomeDispatchResult(
            request_id=payload.request_id,
            kind="clarify",
            reason=reason,
            confidence=0.5,
            decided_by="rule",
            expires_at=expires_at,
            clarification=clarification,
        )

    def _out_of_scope_result(
        self,
        owner_id: str,
        payload: HomeDispatchRequest,
        candidates: list[LearningWorkspace],
        *,
        reason: str,
        now: datetime,
    ) -> HomeDispatchResult:
        recovery = self._clarify_result(
            owner_id,
            payload,
            candidates,
            reason=reason,
            now=now,
        ).clarification
        return HomeDispatchResult(
            request_id=payload.request_id,
            kind="out_of_scope",
            reason=reason,
            confidence=0.98,
            decided_by="rule",
            expires_at=now + timedelta(minutes=10),
            manual_recovery=recovery,
            limitations=["不提供实时事实、医疗、法律、投资或破坏性操作"],
        )

    def _model_unconfigured_result(
        self,
        owner_id: str,
        payload: HomeDispatchRequest,
        summaries: list[WorkspaceDispatchSummary],
        *,
        is_admin: bool,
        now: datetime,
    ) -> HomeDispatchResult:
        if summaries:
            chosen = sorted(summaries, key=lambda item: self._rank_summary(item, now))[0]
            candidates = self._workspace_service.list(owner_id)
            return self._open_workspace_result(
                owner_id,
                payload,
                chosen.id,
                candidates,
                reason="一次性回答需要管理员启用模型；你仍可进入学习空间继续。",
                explicit=False,
                truncated=False,
                now=now,
                confidence=1,
                decided_by="rule",
            )
        return HomeDispatchResult(
            request_id=payload.request_id,
            kind="out_of_scope",
            reason="这类一次性问题需要管理员启用模型。",
            confidence=1,
            decided_by="rule",
            expires_at=now + timedelta(minutes=10),
            limitations=[
                "管理员可前往 /admin/integrations/chat 配置模型"
                if is_admin
                else "你仍可以先创建或进入学习空间"
            ],
        )

    def _deterministic_model_fallback(
        self,
        owner_id: str,
        payload: HomeDispatchRequest,
        candidates: list[LearningWorkspace],
        *,
        truncated: bool,
        now: datetime,
    ) -> HomeDispatchResult:
        named = [item for item in candidates if item.title.casefold() in payload.text.casefold()]
        if len(named) == 1:
            return self._open_workspace_result(
                owner_id,
                payload,
                named[0].id,
                candidates,
                reason="语义模型暂不可用，按明确名称匹配已有空间。",
                explicit=False,
                truncated=truncated,
                now=now,
                confidence=1,
                decided_by="rule",
            )
        return self._clarify_result(
            owner_id,
            payload,
            candidates,
            reason="语义模型暂不可用，请手动选择处理方式。",
            now=now,
        )

    def confirm(
        self,
        owner_id: str,
        payload: HomeConfirmRequest,
        *,
        now: datetime | None = None,
    ) -> HomeActionReceipt:
        observed_at = (now or datetime.now(UTC)).astimezone(UTC)
        existing = self._receipts.get(owner_id, payload.idempotency_key)
        if existing is not None:
            if existing.request_id != payload.request_id:
                raise HomeConfirmationError("Idempotency key belongs to another request")
            return existing.model_copy(update={"replayed": True})
        proposal_type = payload.proposal.get("proposal_type")
        try:
            if proposal_type == "create_workspace":
                proposal = WorkspaceProposal.model_validate(payload.proposal)
                operation = "create_workspace"
                signed_payload = _workspace_proposal_payload(proposal)
            elif proposal_type == "workspace_action":
                proposal = WorkspaceActionProposal.model_validate(payload.proposal)
                operation = proposal.action_type
                signed_payload = _action_proposal_payload(proposal)
            else:
                raise HomeConfirmationError("Unknown home action proposal")
            claims = self._signer.verify(
                payload.confirmation_token,
                owner_id=owner_id,
                operation=operation,
                now=observed_at,
            )
        except (ValidationError, HomeTokenError) as error:
            raise HomeConfirmationError(str(error)) from error
        if proposal.confirmation_token != payload.confirmation_token:
            raise HomeConfirmationError("Proposal token does not match request token")
        if proposal.idempotency_key != payload.idempotency_key:
            raise HomeConfirmationError("Proposal idempotency key does not match")
        if claims.proposal_hash != proposal_hash(signed_payload):
            raise HomeConfirmationError("Proposal fields were changed after signing")
        if operation == "create_workspace":
            return self._confirm_workspace(
                owner_id,
                payload,
                proposal,
                claims.state_hash,
                observed_at,
            )
        return self._confirm_workspace_action(
            owner_id, payload, proposal, claims.state_hash, observed_at
        )

    def _confirm_workspace(
        self,
        owner_id: str,
        request: HomeConfirmRequest,
        proposal: WorkspaceProposal,
        workspace_snapshot_hash: str,
        now: datetime,
    ) -> HomeActionReceipt:
        preview = WorkspaceResolutionPreview(
            payload=WorkspaceResolveRequest(
                intent=proposal.goal,
                exam_at=proposal.exam_at,
                daily_minutes=proposal.daily_minutes,
            ),
            decision=WorkspaceRoutingDecision(
                action="created",
                title=proposal.title,
                subject=proposal.subject,
                topics=proposal.topics,
                keywords=proposal.keywords,
                confidence=1,
                reason=proposal.reason,
            ),
            workspace_snapshot_hash=workspace_snapshot_hash,
            observed_at=now,
        )
        try:
            route = self._workspace_service.commit_resolution(owner_id, preview)
        except WorkspaceConflictError as error:
            raise HomeActionConflictError(str(error)) from error
        target = WorkspaceTarget(
            workspace_id=route.workspace.id,
            title=route.workspace.title,
            reason=route.reason,
            match_kind="explicit_command",
            auto_navigate=True,
            route_action=route.action,
        )
        receipt = HomeActionReceipt(
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            operation="create_workspace",
            status="succeeded",
            workspace_id=route.workspace.id,
            affected_refs=[route.workspace.id],
            after_version=self._learning.get(owner_id, route.workspace.id).version,
            undoable=True,
            route=target,
        )
        return self._receipts.save(owner_id, receipt)

    def _confirm_workspace_action(
        self,
        owner_id: str,
        request: HomeConfirmRequest,
        proposal: WorkspaceActionProposal,
        version: str,
        now: datetime,
    ) -> HomeActionReceipt:
        del now
        try:
            before_record = self._learning.get(owner_id, proposal.workspace_id)
        except Exception as error:
            raise HomeActionConflictError("Target workspace is unavailable") from error
        if str(before_record.version) != version:
            raise HomeActionConflictError("Learning plan changed; generate a new preview")
        session_id = proposal.affected_refs[0]
        update = PlanSessionUpdate(
            planned_at=(
                datetime.fromisoformat(str(proposal.after["planned_at"]))
                if proposal.action_type == "reschedule_session"
                else None
            ),
            minutes=(
                int(proposal.after["minutes"])
                if proposal.action_type == "adjust_session_minutes"
                else None
            ),
        )
        self._learning_service.update_plan_session(
            owner_id,
            proposal.workspace_id,
            session_id,
            update,
        )
        after_record = self._learning.get(owner_id, proposal.workspace_id)
        receipt = HomeActionReceipt(
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            operation=proposal.action_type,
            status="succeeded",
            workspace_id=proposal.workspace_id,
            affected_refs=proposal.affected_refs,
            before_version=before_record.version,
            after_version=after_record.version,
            undoable=True,
        )
        return self._receipts.save(owner_id, receipt)
