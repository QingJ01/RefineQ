"""Small in-process request limits for single-instance and local deployments."""

from __future__ import annotations

from collections import defaultdict, deque
from hashlib import sha256
from math import ceil
from threading import RLock
from time import monotonic

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response


class SlidingWindowRateLimiter:
    """Thread-safe monotonic sliding windows keyed by untrusted-client scope."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
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
            events = self._events[key]
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
