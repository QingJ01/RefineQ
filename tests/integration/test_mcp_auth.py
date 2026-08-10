from __future__ import annotations

import asyncio
import json

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.testclient import TestClient

from refineq.mcp.auth import AccountBoundMcpGateway
from refineq.mcp.observability import McpTelemetry


def _gateway(
    *,
    read_limit: int = 10,
    write_limit: int = 10,
    telemetry: McpTelemetry | None = None,
):
    async def endpoint(_request):
        return JSONResponse({"ok": True})

    child = Starlette()
    child.add_route("/", endpoint, methods=["GET", "POST"])
    return AccountBoundMcpGateway(
        child,
        principal_id="user_bound",
        account_email="qingj1314@163.com",
        read_limit=read_limit,
        write_limit=write_limit,
        window_seconds=60,
        telemetry=telemetry,
    )


def test_mcp_gateway_accepts_requests_without_bearer_credentials() -> None:
    with TestClient(_gateway()) as client:
        missing = client.get("/")
        legacy_header = client.get("/", headers={"Authorization": "Bearer ignored"})

    assert missing.status_code == 200
    assert legacy_header.status_code == 200
    assert "www-authenticate" not in missing.headers


def test_mcp_auth_uses_independent_read_and_write_rate_limits() -> None:
    read_body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    write_body = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "refineq_begin_demo", "arguments": {}},
    }
    with TestClient(_gateway(read_limit=1, write_limit=1)) as client:
        assert client.post("/", json=read_body).status_code == 200
        read_limited = client.post("/", json=read_body)
        assert client.post("/", json=write_body).status_code == 200
        write_limited = client.post("/", json=write_body)

    assert read_limited.status_code == 429
    assert write_limited.status_code == 429
    assert read_limited.headers["retry-after"] == "60"


def test_begin_demo_has_a_stricter_reset_bucket_than_other_writes() -> None:
    begin = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "refineq_begin_demo", "arguments": {}},
    }
    practice = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "refineq_get_practice_task", "arguments": {}},
    }
    with TestClient(_gateway(write_limit=6)) as client:
        assert client.post("/", json=begin).status_code == 200
        assert client.post("/", json=begin).status_code == 200
        reset_limited = client.post("/", json=begin)
        ordinary_write = client.post("/", json=practice)

    assert reset_limited.status_code == 429
    assert ordinary_write.status_code == 200


def test_mcp_gateway_bounds_the_body_before_json_parsing() -> None:
    with TestClient(_gateway()) as client:
        response = client.post("/", content=b"x" * (128 * 1024 + 1))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_body_too_large"


def test_mcp_gateway_records_only_bounded_transport_categories() -> None:
    telemetry = McpTelemetry()
    headers = {
        "Mcp-Protocol-Version": "2026-07-28",
        "User-Agent": "python-httpx/0.28",
    }
    with TestClient(_gateway(telemetry=telemetry)) as client:
        assert client.get("/", headers=headers).status_code == 200

    snapshot = telemetry.snapshot()
    assert snapshot["protocol_versions"] == {"2026-07-28": 1}
    assert snapshot["client_classes"] == {"sdk": 1}
    assert "python-httpx" not in str(snapshot)


def test_mcp_gateway_collapses_unknown_protocol_versions_to_one_bucket() -> None:
    telemetry = McpTelemetry()
    headers = {
        "Mcp-Protocol-Version": "attacker-controlled-version",
    }
    with TestClient(_gateway(telemetry=telemetry)) as client:
        assert client.get("/", headers=headers).status_code == 200

    assert telemetry.snapshot()["protocol_versions"] == {"other": 1}


@pytest.mark.asyncio
async def test_mcp_gateway_times_out_a_stalled_body() -> None:
    async def child(_scope, _receive, _send):
        raise AssertionError("stalled body must not reach the MCP application")

    gateway = AccountBoundMcpGateway(
        child,
        principal_id="user_bound",
        account_email="qingj1314@163.com",
        read_limit=10,
        write_limit=10,
        window_seconds=60,
        body_read_timeout_seconds=0.01,
    )
    sent: list[dict] = []

    async def stalled_receive():
        await asyncio.sleep(60)
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    await gateway(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "client": ("127.0.0.1", 1234),
        },
        stalled_receive,
        send,
    )

    assert sent[0]["status"] == 408
    payload = json.loads(sent[1]["body"])
    assert payload["error"]["code"] == "request_timeout"
