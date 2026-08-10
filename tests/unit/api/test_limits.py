"""Request-boundary tests that run before FastAPI parses endpoint bodies."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from refineq.api.app import create_app
from refineq.api.limits import (
    RequestBodyLimitMiddleware,
    UploadAdmissionController,
)
from refineq.config import Settings
from refineq.rate_limits import SlidingWindowRateLimiter


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


@pytest.mark.asyncio
async def test_idle_chunked_upload_timeout_overrides_a_downstream_400() -> None:
    outgoing: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        await asyncio.sleep(0.1)
        return {"type": "http.request", "body": b"x", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        outgoing.append(message)

    async def swallow_timeout(scope, receive, send) -> None:
        try:
            await receive()
        except RuntimeError:
            response = {"type": "http.response.start", "status": 400, "headers": []}
            await send(response)
            await send({"type": "http.response.body", "body": b"bad multipart"})

    controller = UploadAdmissionController(max_global=1, max_per_owner=1)
    middleware = RequestBodyLimitMiddleware(
        swallow_timeout,
        max_bytes=100,
        body_idle_timeout_seconds=0.01,
        body_total_timeout_seconds=1.0,
        admission=controller,
    )
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/projects/project/materials",
        "headers": [(b"transfer-encoding", b"chunked")],
    }
    await middleware(scope, receive, send)

    assert outgoing[0]["status"] == 408
    assert json.loads(outgoing[1]["body"])["error"]["code"] == "upload_body_timeout"

    after_release: list[dict[str, Any]] = []

    async def send_after_release(message: dict[str, Any]) -> None:
        after_release.append(message)

    await middleware(scope, receive, send_after_release)
    assert after_release[0]["status"] == 408


@pytest.mark.asyncio
async def test_total_chunked_upload_timeout_is_independent_of_chunk_activity() -> None:
    incoming = iter(
        [
            {"type": "http.request", "body": b"x", "more_body": True},
            {"type": "http.request", "body": b"y", "more_body": False},
        ]
    )
    outgoing: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        await asyncio.sleep(0.03)
        return next(incoming)

    async def send(message: dict[str, Any]) -> None:
        outgoing.append(message)

    async def consume(scope, receive, send) -> None:
        while (await receive()).get("more_body"):
            pass

    middleware = RequestBodyLimitMiddleware(
        consume,
        max_bytes=100,
        body_idle_timeout_seconds=0.2,
        body_total_timeout_seconds=0.05,
    )
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

    assert outgoing[0]["status"] == 408
    assert json.loads(outgoing[1]["body"])["error"]["code"] == "upload_body_timeout"


def test_real_chunked_multipart_returns_the_stable_413_contract(tmp_path: Path) -> None:
    boundary = "refineq-boundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="files"; filename="notes.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n" + ("x" * 120) + f"\r\n--{boundary}--\r\n"
    ).encode()

    def chunks():
        yield body[:80]
        yield body[80:]

    with TestClient(_app(tmp_path)) as client:
        response = client.post(
            "/workspaces/space/materials",
            content=chunks(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_body_too_large"


@pytest.mark.asyncio
async def test_upload_admission_rejects_before_a_second_request_reaches_the_app() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    app_calls = 0

    async def blocked_app(scope, receive, send) -> None:
        nonlocal app_calls
        app_calls += 1
        entered.set()
        await release.wait()

    controller = UploadAdmissionController(max_global=1, max_per_owner=1)
    middleware = RequestBodyLimitMiddleware(
        blocked_app,
        max_bytes=1_000,
        admission=controller,
    )
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/projects/project/materials",
        "headers": [],
        "client": ("198.51.100.1", 50000),
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    first_messages: list[dict[str, Any]] = []

    async def send_first(message: dict[str, Any]) -> None:
        first_messages.append(message)

    first = asyncio.create_task(middleware(scope, receive, send_first))
    await entered.wait()
    rejected: list[dict[str, Any]] = []

    async def send_rejected(message: dict[str, Any]) -> None:
        rejected.append(message)

    await middleware(scope, receive, send_rejected)
    release.set()
    await first

    assert app_calls == 1
    assert rejected[0]["status"] == 503
    assert json.loads(rejected[1]["body"])["error"]["code"] == "upload_capacity_exceeded"


@pytest.mark.asyncio
async def test_upload_admission_groups_distinct_tokens_by_verified_user() -> None:
    entered = asyncio.Event()
    release = asyncio.Event()
    app_calls = 0

    async def blocked_app(scope, receive, send) -> None:
        nonlocal app_calls
        app_calls += 1
        entered.set()
        await release.wait()

    class Identity:
        def verify_token(self, token: str):
            assert token in {"token-one", "token-two"}
            return SimpleNamespace(id="user-1")

    controller = UploadAdmissionController(max_global=2, max_per_owner=1)
    middleware = RequestBodyLimitMiddleware(
        blocked_app,
        max_bytes=1_000,
        admission=controller,
    )
    base_scope = {
        "type": "http",
        "method": "POST",
        "path": "/projects/project/materials",
        "client": ("198.51.100.1", 50000),
        "app": SimpleNamespace(state=SimpleNamespace(identity=Identity())),
    }

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    first_scope = {
        **base_scope,
        "headers": [(b"authorization", b"Bearer token-one")],
    }
    second_scope = {
        **base_scope,
        "headers": [(b"authorization", b"Bearer token-two")],
    }
    first_messages: list[dict[str, Any]] = []

    async def send_first(message: dict[str, Any]) -> None:
        first_messages.append(message)

    first = asyncio.create_task(middleware(first_scope, receive, send_first))
    await entered.wait()
    rejected: list[dict[str, Any]] = []

    async def send_rejected(message: dict[str, Any]) -> None:
        rejected.append(message)

    await middleware(second_scope, receive, send_rejected)
    release.set()
    await first

    assert app_calls == 1
    assert rejected[0]["status"] == 429
    assert json.loads(rejected[1]["body"])["error"]["code"] == "upload_concurrency_exceeded"


def test_two_external_clients_receive_independent_auth_windows(tmp_path: Path) -> None:
    app = _app(tmp_path)
    payload = {"email": "missing@example.com", "password": "wrong-password"}

    with TestClient(app, client=("198.51.100.10", 50000)) as first:
        assert first.post("/auth/login", json=payload).status_code == 401
        assert first.post("/auth/login", json=payload).status_code == 429
    with TestClient(app, client=("203.0.113.20", 50000)) as second:
        assert second.post("/auth/login", json=payload).status_code == 401


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/auth/password-reset/request", {"email": "missing@example.com"}),
        (
            "/auth/password-reset/complete",
            {"token": "invalid-token", "password": "new-correct-horse-battery-staple"},
        ),
    ],
)
def test_password_reset_endpoints_use_the_auth_rate_limit(
    tmp_path: Path,
    path: str,
    payload: dict[str, str],
) -> None:
    with TestClient(_app(tmp_path)) as client:
        first = client.post(path, json=payload)
        second = client.post(path, json=payload)

    assert first.status_code != 429
    assert second.status_code == 429


def test_rate_limiter_prunes_expired_keys_and_caps_new_key_growth() -> None:
    limiter = SlidingWindowRateLimiter(max_keys=2)

    assert limiter.check("first", limit=5, window_seconds=10, now=0) is None
    assert limiter.check("second", limit=5, window_seconds=10, now=0) is None
    assert limiter.check("third", limit=5, window_seconds=10, now=1) == 9
    assert limiter.check("third", limit=5, window_seconds=10, now=11) is None
