"""Small in-process request limits for single-instance and local deployments."""

from __future__ import annotations

from asyncio import timeout as async_timeout
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

from refineq.identity.service import InvalidTokenError


class RequestBodyTooLargeError(RuntimeError):
    """Internal signal raised before multipart parsing can exceed its byte budget."""


class RequestBodyTimeoutError(RuntimeError):
    """Internal signal raised when an upload body is sent too slowly."""


class UploadAdmissionController:
    """Reject excess upload concurrency without queueing request bodies in memory."""

    def __init__(self, *, max_global: int, max_per_owner: int) -> None:
        if max_global < 1 or max_per_owner < 1:
            raise ValueError("upload concurrency limits must be positive")
        self._max_global = max_global
        self._max_per_owner = max_per_owner
        self._active_global = 0
        self._active_by_owner: dict[str, int] = {}
        self._lock = RLock()

    def acquire_global(self) -> bool:
        with self._lock:
            if self._active_global >= self._max_global:
                return False
            self._active_global += 1
            return True

    def acquire_owner(self, owner_key: str) -> bool:
        with self._lock:
            active = self._active_by_owner.get(owner_key, 0)
            if active >= self._max_per_owner:
                return False
            self._active_by_owner[owner_key] = active + 1
            return True

    def release(self, owner_key: str | None) -> None:
        with self._lock:
            if owner_key is not None:
                active = self._active_by_owner.get(owner_key, 0)
                if active <= 1:
                    self._active_by_owner.pop(owner_key, None)
                else:
                    self._active_by_owner[owner_key] = active - 1
            if self._active_global > 0:
                self._active_global -= 1


class RequestBodyLimitMiddleware:
    """Count material-upload bytes at the ASGI receive boundary, including chunked bodies."""

    def __init__(
        self,
        app: Any,
        *,
        max_bytes: int,
        body_idle_timeout_seconds: float = 10.0,
        body_total_timeout_seconds: float = 60.0,
        admission: UploadAdmissionController | None = None,
    ) -> None:
        if body_idle_timeout_seconds <= 0 or body_total_timeout_seconds <= 0:
            raise ValueError("upload body timeouts must be positive")
        self.app = app
        self._max_bytes = max_bytes
        self._body_idle_timeout_seconds = body_idle_timeout_seconds
        self._body_total_timeout_seconds = body_total_timeout_seconds
        self._admission = admission

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

    @staticmethod
    async def _reject_timeout(scope: dict[str, Any], receive: Any, send: Any) -> None:
        response = JSONResponse(
            status_code=408,
            content={
                "error": {
                    "code": "upload_body_timeout",
                    "message": "Material upload body was not received within the time limit",
                }
            },
        )
        await response(scope, receive, send)

    @staticmethod
    async def _reject_admission(
        scope: dict[str, Any],
        receive: Any,
        send: Any,
        *,
        global_limit: bool,
    ) -> None:
        response = JSONResponse(
            status_code=503 if global_limit else 429,
            content={
                "error": {
                    "code": (
                        "upload_capacity_exceeded"
                        if global_limit
                        else "upload_concurrency_exceeded"
                    ),
                    "message": "Too many material uploads are active; retry later",
                }
            },
            headers={"Retry-After": "1"},
        )
        await response(scope, receive, send)

    @staticmethod
    def _owner_key(scope: dict[str, Any]) -> str:
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        authorization = headers.get(b"authorization", b"").decode("latin-1")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            try:
                user = scope["app"].state.identity.verify_token(token)
            except (InvalidTokenError, AttributeError, KeyError):
                return f"credential:{sha256(token.encode('utf-8')).hexdigest()[:20]}"
            return f"user:{user.id}"
        client = scope.get("client")
        host = client[0] if client else "unknown"
        return f"anonymous:{host}"

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if not self._is_material_upload(scope):
            await self.app(scope, receive, send)
            return

        owner_key: str | None = None
        if self._admission is not None:
            if not self._admission.acquire_global():
                await self._reject_admission(
                    scope,
                    receive,
                    send,
                    global_limit=True,
                )
                return
            try:
                owner_key = self._owner_key(scope)
            except Exception:
                self._admission.release(None)
                raise
            if not self._admission.acquire_owner(owner_key):
                self._admission.release(None)
                await self._reject_admission(
                    scope,
                    receive,
                    send,
                    global_limit=False,
                )
                return

        try:
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
            exceeded = False
            timed_out = False
            body_started_at: float | None = None
            downstream_messages: list[dict[str, Any]] = []

            async def limited_receive() -> dict[str, Any]:
                nonlocal body_started_at, exceeded, received, timed_out
                if body_started_at is None:
                    body_started_at = monotonic()
                remaining_total = self._body_total_timeout_seconds - (monotonic() - body_started_at)
                receive_budget = min(self._body_idle_timeout_seconds, remaining_total)
                if receive_budget <= 0:
                    timed_out = True
                    raise RequestBodyTimeoutError
                try:
                    async with async_timeout(receive_budget):
                        message = await receive()
                except TimeoutError as error:
                    timed_out = True
                    raise RequestBodyTimeoutError from error
                if message.get("type") == "http.request":
                    received += len(message.get("body", b""))
                    if received > self._max_bytes:
                        exceeded = True
                        raise RequestBodyTooLargeError
                return message

            async def buffered_send(message: dict[str, Any]) -> None:
                downstream_messages.append(message)

            try:
                await self.app(scope, limited_receive, buffered_send)
            except RequestBodyTooLargeError:
                exceeded = True
            except RequestBodyTimeoutError:
                timed_out = True

            if timed_out:
                await self._reject_timeout(scope, receive, send)
                return
            if exceeded:
                await self._reject(scope, receive, send)
                return
            for message in downstream_messages:
                await send(message)
        finally:
            if self._admission is not None:
                self._admission.release(owner_key)


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
