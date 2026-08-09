"""Transport-independent in-process rate-limit primitives."""

from __future__ import annotations

from collections import deque
from math import ceil
from threading import RLock
from time import monotonic


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
