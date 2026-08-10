"""Typed public contracts for the RefineQ MCP evaluation tools."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator


class McpError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False
    retry_after_ms: int | None = Field(default=None, ge=0)
    next_action: str | None = Field(default=None, max_length=100)


class ToolOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = "1"
    warnings: list[str] = Field(default_factory=list, max_length=8)

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        schema = handler(core_schema)
        required = schema.setdefault("required", [])
        if "schema_version" not in required:
            required.insert(0, "schema_version")
        return schema


class ToolFailure(ToolOutput):
    schema_version: Literal["1"]
    error: McpError


class BeginDemoOutput(ToolOutput):
    run_id: str
    expires_at: str
    simulation: bool
    account: dict[str, str]
    space: dict[str, Any]
    runtime: dict[str, Any]
    next_tool: str


class LearningContextOutput(ToolOutput):
    run_id: str
    workspace: dict[str, Any]
    topics: list[dict[str, Any]]
    today_sessions: list[dict[str, Any]]
    pending_question: dict[str, Any] | None
    materials: dict[str, Any]
    latest_evidence: list[dict[str, Any]]
    next_action: dict[str, Any]
    state_version: int
    truncated: bool = False
    simulation: bool


class MaterialSearchOutput(ToolOutput):
    run_id: str
    query: str
    retrieval_mode: Literal["hybrid", "lexical"]
    results: list[dict[str, Any]]
    truncated: bool = False


class PracticeTaskOutput(ToolOutput):
    run_id: str
    request_id: str
    question_id: str
    topic_id: str
    prompt: str
    difficulty: int = Field(ge=1, le=5)
    citations: list[str]
    grounding: Literal["material"]
    mode: Literal["ai", "fallback"]
    state_version: int
    simulation: bool


class SubmitAnswerOutput(ToolOutput):
    run_id: str
    attempt_id: str
    question_id: str
    score: int = Field(ge=0, le=100)
    passed: bool
    strengths: list[str]
    gaps: list[str]
    misconceptions: list[str]
    citations: list[str]
    grading_mode: Literal["ai", "fallback"]
    evidence_source: Literal["mcp_relayed"]
    simulation: bool
    mastery_effect: dict[str, Any]
    final_state: dict[str, Any]
    next_action: dict[str, Any]


class _ObjectUnionSchema:
    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        schema = handler(core_schema)
        schema["type"] = "object"
        return schema


class BeginDemoEnvelope(_ObjectUnionSchema, RootModel[BeginDemoOutput | ToolFailure]):
    pass


class LearningContextEnvelope(_ObjectUnionSchema, RootModel[LearningContextOutput | ToolFailure]):
    pass


class MaterialSearchEnvelope(_ObjectUnionSchema, RootModel[MaterialSearchOutput | ToolFailure]):
    pass


class PracticeTaskEnvelope(_ObjectUnionSchema, RootModel[PracticeTaskOutput | ToolFailure]):
    pass


class SubmitAnswerEnvelope(_ObjectUnionSchema, RootModel[SubmitAnswerOutput | ToolFailure]):
    pass


class BeginDemoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_run_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{7,127}$")


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=32, max_length=256)


class SearchMaterialsInput(RunInput):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=8)


class PracticeTaskInput(RunInput):
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    topic_id: str | None = Field(default=None, max_length=128)
    difficulty: int = Field(default=3, ge=1, le=5)


class SubmitAnswerInput(RunInput):
    question_id: str = Field(min_length=1, max_length=256)
    answer: str = Field(min_length=1, max_length=10_000)
    attempt_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    expected_state_version: int = Field(ge=1)


class RuntimeCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    configured: bool
    mode: str


class RuntimeStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    question: RuntimeCapability
    grading: RuntimeCapability
    retrieval: RuntimeCapability
    observed_at: str | None = None
    stale: bool = True

    @model_validator(mode="after")
    def stale_without_observation(self) -> RuntimeStatus:
        if self.observed_at is None and not self.stale:
            raise ValueError("runtime without an observation must be stale")
        return self
