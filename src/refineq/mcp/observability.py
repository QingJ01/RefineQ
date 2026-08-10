"""Bounded, content-free operational metrics for the MCP evaluation surface."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from threading import RLock
from typing import Any


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return round(ordered[index], 3)


def _client_class(user_agent: str) -> str:
    normalized = user_agent.casefold()
    if "inspector" in normalized:
        return "inspector"
    if "python-httpx" in normalized or "mcp" in normalized:
        return "sdk"
    if not normalized:
        return "unknown"
    return "other"


@dataclass(frozen=True, slots=True)
class ToolObservation:
    tool: str
    outcome: str
    error_code: str
    mode: str
    duration_ms: float
    response_bytes: int


class McpTelemetry:
    """Keep bounded process metrics without retaining request or response content."""

    def __init__(self, *, sample_limit: int = 2_048) -> None:
        self._lock = RLock()
        self._sample_limit = sample_limit
        self._tool_calls: Counter[tuple[str, str, str, str]] = Counter()
        self._durations: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=self._sample_limit)
        )
        self._response_sizes: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=self._sample_limit)
        )
        self._events: Counter[str] = Counter()
        self._protocol_versions: Counter[str] = Counter()
        self._client_classes: Counter[str] = Counter()

    def record_tool(self, observation: ToolObservation) -> None:
        with self._lock:
            self._tool_calls[
                (
                    observation.tool,
                    observation.outcome,
                    observation.error_code,
                    observation.mode,
                )
            ] += 1
            self._durations[observation.tool].append(max(0.0, observation.duration_ms))
            self._response_sizes[observation.tool].append(float(max(0, observation.response_bytes)))

    def record_event(self, event: str) -> None:
        with self._lock:
            self._events[event] += 1

    def record_transport(self, *, protocol_version: str, user_agent: str) -> None:
        bounded_version = (
            protocol_version
            if protocol_version in {"2026-07-28", "2025-11-25"}
            else "unspecified"
            if not protocol_version
            else "other"
        )
        with self._lock:
            self._protocol_versions[bounded_version] += 1
            self._client_classes[_client_class(user_agent)] += 1

    @staticmethod
    def _samples(values: list[float]) -> dict[str, float | int]:
        return {
            "count": len(values),
            "p50": _percentile(values, 0.50),
            "p95": _percentile(values, 0.95),
            "p99": _percentile(values, 0.99),
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            calls = [
                {
                    "tool": tool,
                    "outcome": outcome,
                    "error_code": error_code or None,
                    "mode": mode or None,
                    "count": count,
                }
                for (tool, outcome, error_code, mode), count in sorted(self._tool_calls.items())
            ]
            durations = {
                tool: self._samples(list(values)) for tool, values in self._durations.items()
            }
            response_sizes = {
                tool: self._samples(list(values)) for tool, values in self._response_sizes.items()
            }
            return {
                "tool_calls": calls,
                "duration_ms": durations,
                "response_bytes": response_sizes,
                "events": dict(self._events),
                "protocol_versions": dict(self._protocol_versions),
                "client_classes": dict(self._client_classes),
            }
