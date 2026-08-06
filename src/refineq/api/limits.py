"""Small in-process request limits for single-instance and local deployments."""

from __future__ import annotations

from collections import deque
from hashlib import sha256
from math import ceil
from threading import RLock
from time import monotonic
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class RequestBodyTooLargeError(RuntimeError):
    """Internal signal raised before multipart parsing can exceed its byte budget."""


class RequestBodyLimitMiddleware:
    """Count material-upload bytes at the ASGI receive boundary, including chunked bodies."""

    def __init__(self, app: Any, *, max_bytes: int) -> None:
        self.app = app
        self._max_bytes = max_bytes

    @staticmethod
    def _is_material_upload(scope: dict[str, Any]) -> bool:
        path = scope.get("path", "")
        parts = path.strip("/").split("/")
        return (
            scope.get("type") == "http"
            and scope.get("method") == "POST"
            and len(parts) == 3
            and parts[0] in {"projects", "workspaces"}
            and parts[2] == "materials"
        )

    @staticmethod
    async def _reject(scope: dict[str, Any], receive: Any, send: Any) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "request_body_too_large",
                    "message": "Request body exceeds the material upload limit",
                }
            },
        )
        await response(scope, receive, send)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if not self._is_material_upload(scope):
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = 0
            if declared_size > self._max_bytes:
                await self._reject(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal received
            message = await receive()
            if message.get("type") == "http.request":
                received += len(message.get("body", b""))
                if received > self._max_bytes:
                    raise RequestBodyTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except RequestBodyTooLargeError:
            await self._reject(scope, receive, send)


class SlidingWindowRateLimiter:
    """Thread-safe monotonic sliding windows keyed by untrusted-client scope."""

    def __init__(self, *, max_keys: int = 10_000) -> None:
        if max_keys < 1:
            raise ValueError("max_keys must be positive")
        self._events: dict[str, deque[float]] = {}
        self._max_keys = max_keys
        self._lock = RLock()

    def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: float,
        now: float | None = None,
    ) -> int | None:
        observed_at = monotonic() if now is None else now
        cutoff = observed_at - window_seconds
        with self._lock:
            events = self._events.get(key)
            if events is None:
                if len(self._events) >= self._max_keys:
                    for event_key, prior_events in list(self._events.items()):
                        while prior_events and prior_events[0] <= cutoff:
                            prior_events.popleft()
                        if not prior_events:
                            self._events.pop(event_key, None)
                if len(self._events) >= self._max_keys:
                    oldest = min(prior_events[0] for prior_events in self._events.values())
                    return max(1, ceil(window_seconds - (observed_at - oldest)))
                events = deque()
                self._events[key] = events
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return max(1, ceil(window_seconds - (observed_at - events[0])))
            events.append(observed_at)
            return None


class RequestLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        limiter: SlidingWindowRateLimiter,
        auth_limit: int,
        mutation_limit: int,
        window_seconds: float,
    ) -> None:
        super().__init__(app)
        self._limiter = limiter
        self._auth_limit = auth_limit
        self._mutation_limit = mutation_limit
        self._window_seconds = window_seconds

    @staticmethod
    def _client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    @staticmethod
    def _credential_fingerprint(request: Request) -> str:
        authorization = request.headers.get("authorization", "")
        if not authorization:
            return "anonymous"
        return sha256(authorization.encode("utf-8")).hexdigest()[:20]

    @staticmethod
    def _limited_response(retry_after: int) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": "Too many requests; retry later",
                }
            },
            headers={"Retry-After": str(retry_after)},
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        client = self._client_key(request)
        is_auth_request = request.url.path in {"/auth/register", "/auth/login"}
        if is_auth_request:
            retry_after = self._limiter.check(
                f"auth:{client}",
                limit=self._auth_limit,
                window_seconds=self._window_seconds,
            )
            if retry_after is not None:
                return self._limited_response(retry_after)

        if not is_auth_request and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            retry_after = self._limiter.check(
                f"mutation-client:{client}",
                limit=self._mutation_limit,
                window_seconds=self._window_seconds,
            )
            if retry_after is not None:
                return self._limited_response(retry_after)
            fingerprint = self._credential_fingerprint(request)
            retry_after = self._limiter.check(
                f"mutation:{client}:{fingerprint}",
                limit=self._mutation_limit,
                window_seconds=self._window_seconds,
            )
            if retry_after is not None:
                return self._limited_response(retry_after)
        return await call_next(request)
