from __future__ import annotations

import logging

import pytest
from mcp.client import Client

from refineq.mcp.contracts import BeginDemoOutput
from refineq.mcp.server import MCP_TOOL_NAMES, create_mcp_server


class FakeToolService:
    def begin_demo(self, **kwargs):  # pragma: no cover - list-only protocol spike
        raise AssertionError(kwargs)

    def get_learning_context(self, **kwargs):  # pragma: no cover
        raise AssertionError(kwargs)

    def search_materials(self, **kwargs):  # pragma: no cover
        raise AssertionError(kwargs)

    def get_practice_task(self, **kwargs):  # pragma: no cover
        raise AssertionError(kwargs)

    def submit_answer(self, **kwargs):  # pragma: no cover
        raise AssertionError(kwargs)


class SuccessfulBeginService(FakeToolService):
    def begin_demo(self, **_kwargs):
        return BeginDemoOutput(
            run_id="mcp_run_" + "x" * 43,
            expires_at="2026-08-09T12:00:00+00:00",
            simulation=True,
            space={"id": "sandbox"},
            runtime={"stale": False},
            next_tool="refineq_get_learning_context",
        )


@pytest.mark.asyncio
async def test_official_sdk_client_discovers_exactly_five_tools() -> None:
    server = create_mcp_server(FakeToolService())

    async with Client(server) as client:
        tools = (await client.list_tools()).tools
        protocol_version = client.protocol_version

    assert {tool.name for tool in tools} == set(MCP_TOOL_NAMES)
    assert all(tool.output_schema for tool in tools)
    assert protocol_version == "2026-07-28"


@pytest.mark.asyncio
async def test_each_tool_output_schema_requires_a_success_or_error_envelope() -> None:
    async with Client(create_mcp_server(FakeToolService())) as client:
        tools = (await client.list_tools()).tools

    for tool in tools:
        branches = tool.output_schema.get("anyOf", [])
        definitions = tool.output_schema.get("$defs", {})
        required = []
        for branch in branches:
            reference = branch.get("$ref", "")
            resolved = definitions.get(reference.rsplit("/", 1)[-1], {}) if reference else branch
            required.append(set(resolved.get("required", [])))
        assert len(branches) == 2, tool.name
        assert any({"schema_version", "error"} <= fields for fields in required), tool.name
        assert any(
            "schema_version" in fields and "error" not in fields and len(fields) >= 4
            for fields in required
        ), tool.name


@pytest.mark.asyncio
async def test_server_discovery_does_not_advertise_out_of_scope_capabilities() -> None:
    server = create_mcp_server(FakeToolService())

    async with Client(server) as client:
        assert client.server_capabilities is not None
        capabilities = client.server_capabilities.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )

    assert "tasks" not in capabilities
    assert "elicitation" not in capabilities
    assert "resources" not in capabilities
    assert "prompts" not in capabilities


@pytest.mark.asyncio
async def test_successful_tool_call_has_short_text_and_schema_valid_structured_content() -> None:
    server = create_mcp_server(SuccessfulBeginService())

    async with Client(server) as client:
        result = await client.call_tool(
            "refineq_begin_demo",
            {"client_run_key": "external-evaluator-0001"},
        )

    assert result.is_error is False
    assert result.content[0].text == "Evaluation sandbox is ready."
    assert result.structured_content["schema_version"] == "1"


@pytest.mark.asyncio
async def test_unexpected_tool_errors_do_not_log_exception_messages(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sensitive = "mcp_run_sensitive-answer-and-material"

    class FailingService(FakeToolService):
        def begin_demo(self, **_kwargs):
            raise RuntimeError(sensitive)

    with caplog.at_level(logging.ERROR):
        async with Client(create_mcp_server(FailingService())) as client:
            result = await client.call_tool(
                "refineq_begin_demo",
                {"client_run_key": "external-evaluator-0001"},
            )

    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "internal_error"
    assert sensitive not in caplog.text
