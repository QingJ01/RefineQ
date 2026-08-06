"""Request-boundary tests that run before FastAPI parses endpoint bodies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.api.limits import RequestBodyLimitMiddleware, SlidingWindowRateLimiter
from refineq.config import Settings


def _app(tmp_path: Path):
    return create_app(
        Settings(
            data_root=tmp_path / "data",
            material_max_request_bytes=100,
            auth_rate_limit_requests=1,
            mutation_rate_limit_requests=100,
            _env_file=None,
        )
    )


def test_material_content_length_is_rejected_before_route_parsing(tmp_path: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        response = client.post(
            "/workspaces/space/materials",
            content=b"x" * 101,
            headers={"Content-Type": "application/octet-stream"},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_body_too_large"


@pytest.mark.asyncio
async def test_chunked_material_body_is_stopped_at_the_same_limit() -> None:
    incoming = iter(
        [
            {"type": "http.request", "body": b"x" * 60, "more_body": True},
            {"type": "http.request", "body": b"y" * 60, "more_body": False},
        ]
    )
    outgoing: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return next(incoming)

    async def send(message: dict[str, Any]) -> None:
        outgoing.append(message)

    async def consume_body(scope: dict[str, Any], receive, send) -> None:
        while (await receive()).get("more_body"):
            pass

    middleware = RequestBodyLimitMiddleware(consume_body, max_bytes=100)
    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/projects/project/materials",
            "headers": [(b"transfer-encoding", b"chunked")],
        },
        receive,
        send,
    )

    assert outgoing[0]["status"] == 413
    assert json.loads(outgoing[1]["body"])["error"]["code"] == "request_body_too_large"


def test_two_external_clients_receive_independent_auth_windows(tmp_path: Path) -> None:
    app = _app(tmp_path)
    payload = {"email": "missing@example.com", "password": "wrong-password"}

    with TestClient(app, client=("198.51.100.10", 50000)) as first:
        assert first.post("/auth/login", json=payload).status_code == 401
        assert first.post("/auth/login", json=payload).status_code == 429
    with TestClient(app, client=("203.0.113.20", 50000)) as second:
        assert second.post("/auth/login", json=payload).status_code == 401


def test_rate_limiter_prunes_expired_keys_and_caps_new_key_growth() -> None:
    limiter = SlidingWindowRateLimiter(max_keys=2)

    assert limiter.check("first", limit=5, window_seconds=10, now=0) is None
    assert limiter.check("second", limit=5, window_seconds=10, now=0) is None
    assert limiter.check("third", limit=5, window_seconds=10, now=1) == 9
    assert limiter.check("third", limit=5, window_seconds=10, now=11) is None
