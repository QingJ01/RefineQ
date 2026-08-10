"""Official MCP SDK server exposing the five evaluation tools."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from time import perf_counter
from typing import Annotated, Any, TypeVar, cast
from uuid import uuid4

from mcp import types
from mcp.server import MCPServer
from pydantic import Field

from refineq.mcp.contracts import (
    BeginDemoEnvelope,
    BeginDemoOutput,
    LearningContextEnvelope,
    LearningContextOutput,
    MaterialSearchEnvelope,
    MaterialSearchOutput,
    PracticeTaskEnvelope,
    PracticeTaskOutput,
    SubmitAnswerEnvelope,
    SubmitAnswerOutput,
    ToolOutput,
)
from refineq.mcp.errors import McpServiceError, error_result, success_result
from refineq.mcp.observability import McpTelemetry, ToolObservation

logger = logging.getLogger(__name__)
OutputT = TypeVar("OutputT", bound=ToolOutput)

MCP_TOOL_NAMES = (
    "refineq_begin_demo",
    "refineq_get_learning_context",
    "refineq_search_materials",
    "refineq_get_practice_task",
    "refineq_submit_answer",
)

_OUT_OF_SCOPE_REQUEST_HANDLERS = (
    "prompts/get",
    "prompts/list",
    "resources/list",
    "resources/read",
    "resources/templates/list",
    "subscriptions/listen",
)


def _run_tool(
    output_model: type[OutputT],
    operation: Callable[..., OutputT],
    *,
    tool_name: str,
    text: str,
    telemetry: McpTelemetry | None = None,
    **arguments: Any,
) -> OutputT:
    started_at = perf_counter()
    outcome = "success"
    error_code = ""
    mode = ""
    result: types.CallToolResult | None = None
    try:
        result = success_result(operation(**arguments), text=text)
        logger.info(
            "event=mcp_tool_completed tool=%s outcome=success duration_ms=%.1f",
            tool_name,
            (perf_counter() - started_at) * 1000,
        )
        structured = result.structured_content or {}
        mode = str(
            structured.get("mode")
            or structured.get("grading_mode")
            or structured.get("retrieval_mode")
            or ""
        )
        return cast(OutputT, result)
    except McpServiceError as error:
        outcome = "business_error"
        error_code = error.error.code
        logger.info(
            "event=mcp_tool_completed tool=%s outcome=error error_code=%s duration_ms=%.1f",
            tool_name,
            error.error.code,
            (perf_counter() - started_at) * 1000,
        )
        result = error_result(output_model, error.error)
        return cast(OutputT, result)
    except Exception as error:
        outcome = "system_error"
        error_code = "internal_error"
        correlation_id = uuid4().hex
        logger.error(
            "event=mcp_tool_internal_error tool=%s correlation_id=%s "
            "error_type=%s duration_ms=%.1f",
            tool_name,
            correlation_id,
            type(error).__name__,
            (perf_counter() - started_at) * 1000,
        )
        result = error_result(
            output_model,
            McpServiceError(
                "internal_error",
                "The request could not be completed.",
                retryable=True,
            ).error,
            correlation_id=correlation_id,
        )
        return cast(OutputT, result)
    finally:
        if telemetry is not None and result is not None:
            structured = result.structured_content or {}
            response_bytes = len(
                json.dumps(
                    structured,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            )
            telemetry.record_tool(
                ToolObservation(
                    tool=tool_name,
                    outcome=outcome,
                    error_code=error_code,
                    mode=mode,
                    duration_ms=(perf_counter() - started_at) * 1000,
                    response_bytes=response_bytes,
                )
            )


def create_mcp_server(
    tool_service: Any,
    *,
    telemetry: McpTelemetry | None = None,
) -> MCPServer:
    server = MCPServer(
        "RefineQ Evaluation",
        description="A bounded, resettable simulation of the RefineQ learning loop.",
        version="1.0.0",
    )

    write_annotations = types.ToolAnnotations(
        readOnlyHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )
    read_annotations = types.ToolAnnotations(
        readOnlyHint=True,
        idempotentHint=True,
        openWorldHint=False,
    )

    @server.tool(
        name="refineq_begin_demo",
        description="Create or replay one isolated evaluation run.",
        annotations=write_annotations,
    )
    def begin_demo(
        client_run_key: Annotated[
            str,
            Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{7,127}$"),
        ],
    ) -> BeginDemoEnvelope:
        return _run_tool(
            BeginDemoOutput,
            tool_service.begin_demo,
            tool_name="refineq_begin_demo",
            text="Evaluation sandbox is ready.",
            telemetry=telemetry,
            client_run_key=client_run_key,
        )

    @server.tool(
        name="refineq_get_learning_context",
        description="Read a bounded learning context without writing product events.",
        annotations=read_annotations,
    )
    def get_learning_context(
        run_id: Annotated[str, Field(min_length=32, max_length=256)],
    ) -> LearningContextEnvelope:
        return _run_tool(
            LearningContextOutput,
            tool_service.get_learning_context,
            tool_name="refineq_get_learning_context",
            text="Learning context loaded.",
            telemetry=telemetry,
            run_id=run_id,
        )

    @server.tool(
        name="refineq_search_materials",
        description="Search only the indexed material linked to the evaluation workspace.",
        annotations=read_annotations,
    )
    def search_materials(
        run_id: Annotated[str, Field(min_length=32, max_length=256)],
        query: Annotated[str, Field(min_length=1, max_length=500)],
        limit: Annotated[int, Field(ge=1, le=8)] = 5,
    ) -> MaterialSearchEnvelope:
        return _run_tool(
            MaterialSearchOutput,
            tool_service.search_materials,
            tool_name="refineq_search_materials",
            text="Material search completed.",
            telemetry=telemetry,
            run_id=run_id,
            query=query,
            limit=limit,
        )

    @server.tool(
        name="refineq_get_practice_task",
        description="Idempotently obtain one source-grounded practice task.",
        annotations=write_annotations,
    )
    def get_practice_task(
        run_id: Annotated[str, Field(min_length=32, max_length=256)],
        request_id: Annotated[
            str,
            Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"),
        ],
        topic_id: Annotated[str | None, Field(max_length=128)] = None,
        difficulty: Annotated[int, Field(ge=1, le=5)] = 3,
    ) -> PracticeTaskEnvelope:
        return _run_tool(
            PracticeTaskOutput,
            tool_service.get_practice_task,
            tool_name="refineq_get_practice_task",
            text="Source-grounded practice task is ready.",
            telemetry=telemetry,
            run_id=run_id,
            request_id=request_id,
            topic_id=topic_id,
            difficulty=difficulty,
        )

    @server.tool(
        name="refineq_submit_answer",
        description="Idempotently grade an answer inside the simulation and complete the run.",
        annotations=write_annotations,
    )
    def submit_answer(
        run_id: Annotated[str, Field(min_length=32, max_length=256)],
        question_id: Annotated[str, Field(min_length=1, max_length=256)],
        answer: Annotated[str, Field(min_length=1, max_length=10_000)],
        attempt_id: Annotated[
            str,
            Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"),
        ],
        expected_state_version: Annotated[int, Field(ge=1)],
    ) -> SubmitAnswerEnvelope:
        return _run_tool(
            SubmitAnswerOutput,
            tool_service.submit_answer,
            tool_name="refineq_submit_answer",
            text="Answer graded; the evaluation run is complete.",
            telemetry=telemetry,
            run_id=run_id,
            question_id=question_id,
            answer=answer,
            attempt_id=attempt_id,
            expected_state_version=expected_state_version,
        )

    # MCPServer intentionally provides empty prompt/resource handlers by default.
    # Phase A is a tools-only surface, and mcp==2.0.0 is pinned so pruning these
    # handlers is covered by the protocol contract tests below this adapter.
    for method in _OUT_OF_SCOPE_REQUEST_HANDLERS:
        server._lowlevel_server._request_handlers.pop(method, None)

    return server
