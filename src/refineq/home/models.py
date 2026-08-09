"""Strict public and internal values for the home supervisor."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from refineq.learning.next_action import NextAction


class ClarificationSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    continuation_token: str = Field(min_length=1, max_length=4_096)
    option_id: str = Field(min_length=1, max_length=64)


class HomeDispatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=12_000)
    timezone_offset_minutes: int = Field(default=0, ge=-840, le=840)
    clarification: ClarificationSelection | None = None

    @field_validator("request_id", "text", mode="before")
    @classmethod
    def strip_non_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class DirectAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str = Field(min_length=1, max_length=4_000)
    basis: Literal["general_knowledge", "pasted_text"]
    material_grounded: Literal[False] = False
    convertible_goal: str = Field(min_length=1, max_length=500)


class WorkspaceDispatchSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    title: str
    subject: str
    goal: str
    archived: bool = False
    last_active_at: datetime
    exam_at: datetime | None = None
    next_action: NextAction | None = None
    pace_risk: Literal["low", "medium", "high"] = "low"


class WorkspaceTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: str
    title: str
    goal: str
    reason: str = Field(min_length=1, max_length=500)
    match_kind: Literal["explicit_command", "semantic_match"]
    auto_navigate: bool
    route_action: Literal["created", "switched", "reused"] = "reused"
    next_action: NextAction | None = None
    exam_at: datetime | None = None
    pace_risk: Literal["low", "medium", "high"] = "low"
    deferred_workspace_title: str | None = None
    undo_token: str | None = Field(default=None, max_length=4_096)
    undo_expires_at: datetime | None = None

    @field_validator("exam_at", "undo_expires_at", mode="after")
    @classmethod
    def normalize_exam_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("exam_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def explicit_navigation_only(self):
        if self.auto_navigate and self.match_kind != "explicit_command":
            raise ValueError("auto_navigate requires an explicit command")
        if (self.undo_token is None) != (self.undo_expires_at is None):
            raise ValueError("undo token and expiry must be provided together")
        if self.undo_token is not None and self.route_action != "created":
            raise ValueError("only a created workspace can be undone")
        return self


class WorkspaceProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_type: Literal["create_workspace"] = "create_workspace"
    title: str = Field(min_length=1, max_length=200)
    goal: str = Field(min_length=1, max_length=500)
    subject: str = Field(min_length=1, max_length=100)
    topics: list[str] = Field(min_length=1, max_length=20)
    keywords: list[str] = Field(min_length=1, max_length=50)
    exam_at: datetime
    daily_minutes: int = Field(ge=5, le=480)
    material_hint: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=128)
    confirmation_token: str = Field(min_length=1, max_length=4_096)
    expires_at: datetime

    @field_validator("exam_at", "expires_at", mode="after")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value.astimezone(UTC)


class WorkspaceActionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    proposal_type: Literal["workspace_action"] = "workspace_action"
    action_type: Literal["reschedule_session", "adjust_session_minutes"]
    risk_level: Literal["medium"] = "medium"
    workspace_id: str
    workspace_title: str
    before: dict[str, Any]
    after: dict[str, Any]
    affected_refs: list[str] = Field(min_length=1, max_length=20)
    idempotency_key: str = Field(min_length=1, max_length=128)
    confirmation_token: str = Field(min_length=1, max_length=4_096)
    expires_at: datetime

    @field_validator("expires_at", mode="after")
    @classmethod
    def normalize_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        return value.astimezone(UTC)


class ClarificationOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)


class Clarification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question: str = Field(min_length=1, max_length=300)
    options: list[ClarificationOption] = Field(min_length=2, max_length=3)
    continuation_token: str = Field(min_length=1, max_length=4_096)


class HomeDispatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str
    kind: Literal[
        "direct_answer",
        "open_workspace",
        "workspace_action",
        "propose_workspace",
        "clarify",
        "out_of_scope",
    ]
    reason: str = Field(min_length=1, max_length=500)
    confidence: float = Field(ge=0, le=1)
    decided_by: Literal["rule", "model", "hybrid"]
    expires_at: datetime
    answer: DirectAnswer | None = None
    workspace_target: WorkspaceTarget | None = None
    action_proposal: WorkspaceActionProposal | None = None
    workspace_proposal: WorkspaceProposal | None = None
    clarification: Clarification | None = None
    manual_recovery: Clarification | None = None
    limitations: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("expires_at", mode="after")
    @classmethod
    def normalize_expiry(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_variant(self):
        fields = {
            "direct_answer": self.answer,
            "open_workspace": self.workspace_target,
            "workspace_action": self.action_proposal,
            "propose_workspace": self.workspace_proposal,
            "clarify": self.clarification,
        }
        for variant, value in fields.items():
            if (variant == self.kind) != (value is not None):
                raise ValueError(f"{variant} payload does not match result kind")
        if self.kind != "out_of_scope" and self.manual_recovery is not None:
            raise ValueError("manual_recovery is only valid for out_of_scope")
        return self


class HomeConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    confirmation_token: str = Field(min_length=1, max_length=4_096)
    proposal: dict[str, Any]
    idempotency_key: str = Field(min_length=1, max_length=128)


class HomeCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)


class HomeUndoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    undo_token: str = Field(min_length=1, max_length=4_096)


class WorkspaceProposalChanges(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    goal: str | None = Field(default=None, min_length=1, max_length=500)
    exam_at: datetime | None = None
    daily_minutes: int | None = Field(default=None, ge=5, le=480)

    @field_validator("title", "goal", mode="after")
    @classmethod
    def strip_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("exam_at", mode="after")
    @classmethod
    def normalize_optional_datetime(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("exam_at must be timezone-aware")
        return value.astimezone(UTC)


class HomeProposalRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128)
    confirmation_token: str = Field(min_length=1, max_length=4_096)
    original_proposal: WorkspaceProposal
    changes: WorkspaceProposalChanges


class HomeActionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: str
    idempotency_key: str
    operation: Literal[
        "create_workspace",
        "undo_create_workspace",
        "reschedule_session",
        "adjust_session_minutes",
    ]
    status: Literal["succeeded", "conflict", "failed"]
    workspace_id: str
    affected_refs: list[str]
    before_version: int | None = None
    after_version: int | None = None
    undoable: bool = False
    replayed: bool = False
    route: WorkspaceTarget | None = None
