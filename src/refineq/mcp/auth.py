"""Account-bound transport and abuse controls for the MCP endpoint."""

from __future__ import annotations

import json
from asyncio import timeout
from collections import deque
from typing import Any

from starlette.datastructures import URLPath
from starlette.responses import JSONResponse
from starlette.routing import BaseRoute, Match, NoMatchFound, get_route_path
from starlette.types import ASGIApp, Receive, Scope, Send

from refineq.mcp.observability import McpTelemetry
from refineq.rate_limits import SlidingWindowRateLimiter

_READ_TOOLS = {
    "refineq_get_learning_context",
    "refineq_search_materials",
}


class ExactAsgiRoute(BaseRoute):
    """Route one exact HTTP path to an ASGI app without rewriting its scope."""

    def __init__(
        self,
        path: str,
        app: ASGIApp,
        *,
        name: str,
        forward_path: str | None = None,
    ) -> None:
        self.path = path
        self.app = app
        self.name = name
        self.forward_path = forward_path

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        if scope["type"] == "http" and get_route_path(scope) == self.path:
            return Match.FULL, {}
        return Match.NONE, {}

    def url_path_for(self, name: str, /, **path_params: Any) -> URLPath:
        if name == self.name and not path_params:
            return URLPath(self.path, protocol="http")
        raise NoMatchFound(name, path_params)

    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        forwarded_scope = scope
        if self.forward_path is not None:
            forwarded_scope = dict(scope)
            forwarded_scope["path"] = self.forward_path
            forwarded_scope["raw_path"] = self.forward_path.encode("ascii")
        await self.app(forwarded_scope, receive, send)


class AccountBoundMcpGateway:
    """Bind every MCP request to one server-configured account principal."""

    def __init__(
        self,
        app: Any,
        *,
        principal_id: str,
        account_email: str,
        read_limit: int,
        write_limit: int,
        window_seconds: float,
        max_body_bytes: int = 128 * 1024,
        body_read_timeout_seconds: float = 5.0,
        telemetry: McpTelemetry | None = None,
    ) -> None:
        self.app = app
        self._principal_id = principal_id
        self._account_email = account_email
        self._read_limit = read_limit
        self._write_limit = write_limit
        self._window_seconds = window_seconds
        self._max_body_bytes = max_body_bytes
        self._body_read_timeout_seconds = body_read_timeout_seconds
        self._limiter = SlidingWindowRateLimiter()
        self._telemetry = telemetry

    @staticmethod
    async def _body(receive: Any, *, max_bytes: int) -> tuple[bytes, Any, bool]:
        chunks: list[bytes] = []
        size = 0
        too_large = False
        received_request = False
        body_complete = False
        trailing_message: dict[str, Any] | None = None
        while True:
            message = await receive()
            if message.get("type") == "http.request":
                received_request = True
                chunk = message.get("body", b"")
                size += len(chunk)
                if size <= max_bytes:
                    chunks.append(chunk)
                else:
                    too_large = True
                if not message.get("more_body", False):
                    body_complete = True
                    break
            elif message.get("type") == "http.disconnect":
                trailing_message = message
                break
        body = b"".join(chunks)
        cached_messages: deque[dict[str, Any]] = deque()
        if received_request:
            cached_messages.append(
                {
                    "type": "http.request",
                    "body": body,
                    "more_body": not body_complete,
                }
            )
        if trailing_message is not None:
            cached_messages.append(trailing_message)

        async def replay() -> dict[str, Any]:
            if cached_messages:
                return cached_messages.popleft()
            return await receive()

        return body, replay, too_large

    @staticmethod
    def _request_kind(body: bytes) -> str:
        try:
            payload = json.loads(body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return "read"
        if not isinstance(payload, dict) or payload.get("method") != "tools/call":
            return "read"
        params = payload.get("params")
        if not isinstance(params, dict):
            return "read"
        tool_name = params.get("name")
        if tool_name == "refineq_begin_demo":
            return "reset"
        if tool_name in _READ_TOOLS:
            return "read"
        return "write"

    @staticmethod
    async def _respond(
        scope: dict[str, Any],
        receive: Any,
        send: Any,
        *,
        status: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        response = JSONResponse(
            status_code=status,
            content={"error": {"code": code, "message": message}},
            headers=headers,
        )
        await response(scope, receive, send)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        header_pairs = [(key.lower(), value) for key, value in scope.get("headers", [])]
        headers = {key: value for key, value in header_pairs}
        try:
            async with timeout(self._body_read_timeout_seconds):
                body, replay, too_large = await self._body(
                    receive,
                    max_bytes=self._max_body_bytes,
                )
        except TimeoutError:

            async def empty_receive() -> dict[str, Any]:
                return {"type": "http.request", "body": b"", "more_body": False}

            await self._respond(
                scope,
                empty_receive,
                send,
                status=408,
                code="request_timeout",
                message="The MCP request body was not received in time.",
            )
            return
        if too_large:
            await self._respond(
                scope,
                replay,
                send,
                status=413,
                code="request_body_too_large",
                message="The MCP request body exceeds the configured limit.",
            )
            return
        client = scope.get("client")
        client_host = str(client[0]) if client else "unknown"
        kind = self._request_kind(body)
        limit = (
            max(1, self._write_limit // 3)
            if kind == "reset"
            else self._write_limit
            if kind == "write"
            else self._read_limit
        )
        retry_after = None
        for key in (
            f"mcp-principal:{self._principal_id}:{kind}",
            f"mcp-client:{client_host}:{kind}",
        ):
            limited = self._limiter.check(
                key,
                limit=limit,
                window_seconds=self._window_seconds,
            )
            if limited is not None:
                retry_after = max(retry_after or 0, limited)
        if retry_after is not None:
            await self._respond(
                scope,
                replay,
                send,
                status=429,
                code="rate_limited",
                message="Too many evaluation requests; retry later.",
                headers={"Retry-After": str(retry_after)},
            )
            return
        if self._telemetry is not None:
            self._telemetry.record_transport(
                protocol_version=headers.get(b"mcp-protocol-version", b"").decode("latin-1"),
                user_agent=headers.get(b"user-agent", b"").decode("latin-1"),
            )
        scope.setdefault("state", {})["mcp_principal_id"] = self._principal_id
        scope["state"]["mcp_account_email"] = self._account_email
        await self.app(scope, replay, send)
