"""Stable MCP business errors and CallToolResult builders."""

from __future__ import annotations

from typing import TypeVar

from mcp import types

from refineq.mcp.contracts import McpError, ToolFailure, ToolOutput

OutputT = TypeVar("OutputT", bound=ToolOutput)


class McpServiceError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        retry_after_ms: int | None = None,
        next_action: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error = McpError(
            code=code,
            message=message,
            retryable=retryable,
            retry_after_ms=retry_after_ms,
            next_action=next_action,
        )


def success_result(payload: ToolOutput, *, text: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structuredContent=payload.model_dump(mode="json", exclude_none=False),
        isError=False,
    )


def error_result(
    output_model: type[OutputT],
    error: McpError,
    *,
    correlation_id: str | None = None,
) -> types.CallToolResult:
    del correlation_id, output_model
    payload = ToolFailure(schema_version="1", error=error)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=error.message)],
        structuredContent=payload.model_dump(mode="json", exclude_none=True),
        isError=True,
    )
