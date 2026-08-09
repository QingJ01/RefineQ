from __future__ import annotations

import logging

import pytest
from mcp.client import Client

from refineq.mcp.contracts import BeginDemoOutput
from refineq.mcp.observability import McpTelemetry
from refineq.mcp.server import create_mcp_server


class ObservedService:
    def begin_demo(self, **_kwargs):
        return BeginDemoOutput(
            run_id="mcp_run_" + "x" * 43,
            expires_at="2026-08-09T12:00:00+00:00",
            simulation=True,
            space={"id": "sandbox"},
            runtime={"question": {"mode": "fallback"}},
            next_tool="refineq_get_learning_context",
        )


@pytest.mark.asyncio
async def test_tool_metrics_are_bounded_and_logs_exclude_sensitive_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    telemetry = McpTelemetry(sample_limit=8)
    sensitive = "client-key-secret-answer-and-material"
    with caplog.at_level(logging.INFO):
        async with Client(create_mcp_server(ObservedService(), telemetry=telemetry)) as client:
            result = await client.call_tool(
                "refineq_begin_demo",
                {"client_run_key": sensitive},
            )

    assert result.is_error is False
    snapshot = telemetry.snapshot()
    assert snapshot["tool_calls"] == [
        {
            "tool": "refineq_begin_demo",
            "outcome": "success",
            "error_code": None,
            "mode": None,
            "count": 1,
        }
    ]
    assert snapshot["duration_ms"]["refineq_begin_demo"]["count"] == 1
    assert snapshot["response_bytes"]["refineq_begin_demo"]["p99"] > 0
    assert sensitive not in caplog.text
