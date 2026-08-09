from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
from mcp.server.transport_security import TransportSecuritySettings

from refineq.mcp.auth import EvaluationBearerGateway, ExactAsgiRoute
from refineq.mcp.server import create_mcp_server


class FakeToolService:
    def begin_demo(self, **_kwargs):  # pragma: no cover - transport-only
        raise AssertionError

    get_learning_context = begin_demo
    search_materials = begin_demo
    get_practice_task = begin_demo
    submit_answer = begin_demo


def _transport_app() -> FastAPI:
    server = create_mcp_server(FakeToolService())
    child = server.streamable_http_app(
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            allowed_hosts=["testserver"],
            allowed_origins=[],
        ),
    )
    gateway = EvaluationBearerGateway(
        child,
        secret="s" * 48,
        principal_id="evaluation",
        read_limit=20,
        write_limit=10,
        window_seconds=60,
    )

    @asynccontextmanager
    async def lifespan(_app):
        async with child.router.lifespan_context(child):
            yield

    app = FastAPI(lifespan=lifespan)
    app.router.routes.append(ExactAsgiRoute("/mcp", gateway, name="mcp-evaluation"))
    return app


def test_streamable_http_uses_one_exact_mcp_path_and_modern_wire_protocol() -> None:
    discover = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "server/discover",
        "params": {
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientInfo": {
                    "name": "contract-test",
                    "version": "1.0",
                },
                "io.modelcontextprotocol/clientCapabilities": {},
            }
        },
    }
    headers = {
        "Authorization": f"Bearer {'s' * 48}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "Host": "testserver",
        "Mcp-Protocol-Version": "2026-07-28",
        "Mcp-Method": "server/discover",
    }
    with TestClient(_transport_app()) as client:
        response = client.post("/mcp", headers=headers, json=discover)
        duplicate = client.post("/mcp/mcp", headers=headers, json=discover)
        bad_host = client.post(
            "/mcp",
            headers={**headers, "Host": "attacker.example"},
            json=discover,
        )
        unrelated = client.get("/not-an-api-route")

    assert response.status_code == 200
    assert "2026-07-28" in response.json()["result"]["supportedVersions"]
    assert duplicate.status_code == 404
    assert bad_host.status_code == 421
    assert unrelated.status_code == 404
    assert unrelated.headers.get("www-authenticate") is None


def test_prior_stable_protocol_initializes_and_lists_the_same_five_tools() -> None:
    headers = {
        "Authorization": f"Bearer {'s' * 48}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "Host": "testserver",
        "Mcp-Protocol-Version": "2025-11-25",
    }
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "compatibility-test", "version": "1.0"},
        },
    }
    list_tools = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}

    with TestClient(_transport_app()) as client:
        initialized = client.post("/mcp", headers=headers, json=initialize)
        listed = client.post("/mcp", headers=headers, json=list_tools)

    assert initialized.status_code == 200
    assert initialized.json()["result"]["protocolVersion"] == "2025-11-25"
    assert listed.status_code == 200
    assert {item["name"] for item in listed.json()["result"]["tools"]} == {
        "refineq_begin_demo",
        "refineq_get_learning_context",
        "refineq_search_materials",
        "refineq_get_practice_task",
        "refineq_submit_answer",
    }
