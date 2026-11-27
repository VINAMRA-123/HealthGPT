"""In-process latency and usage metrics for chat requests.

Gives p50 / p90 / p95 / p99 latency per answer path without any extra
infrastructure. Numbers cover the most recent ``max_events`` requests since
the server started, so they reset when Render restarts the service. For
long-term numbers, use LangSmith (see ``evals/latency_report.py``).

Percentiles use linear interpolation between the closest ranks, the same
method as ``numpy.percentile``.
"""

import math
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass
from typing import Any


def percentile(values: list[float], pct: float) -> float | None:
    """The ``pct``-th percentile (0-100) of ``values``, or None if empty."""
    if not values:
        return None

    ordered = sorted(values)

    if len(ordered) == 1:
        return float(ordered[0])

    rank = (max(0.0, min(100.0, pct)) / 100) * (len(ordered) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)

    if low == high:
        return float(ordered[int(rank)])

    return float(ordered[low] + (ordered[high] - ordered[low]) * (rank - low))


def summarize(values: list[float], digits: int = 0) -> dict[str, Any]:
    """Count, mean, p50, p90, p95, p99 and max for a list of numbers."""
    if not values:
        return {
            "count": 0,
            "mean": None,
            "p50": None,
            "p90": None,
            "p95": None,
            "p99": None,
            "max": None,
        }

    return {
        "count": len(values),
        "mean": round(sum(values) / len(values), digits),
        "p50": round(percentile(values, 50), digits),
        "p90": round(percentile(values, 90), digits),
        "p95": round(percentile(values, 95), digits),
        "p99": round(percentile(values, 99), digits),
        "max": round(max(values), digits),
    }


def path_for_intent(intent: str) -> str:
    """sql = answered from the database, llm = Gemini, guardrail = refused."""
    if intent == "llm":
        return "llm"

    if intent == "off_topic":
        return "guardrail"

    return "sql"


@dataclass(frozen=True)
class ChatEvent:
    at: float
    path: str
    intent: str
    model: str | None
    status: str  # ok | degraded | error
    latency_ms: float
    first_token_ms: float | None


class ChatMetrics:
    def __init__(self, max_events: int = 2000) -> None:
        self._events: deque[ChatEvent] = deque(maxlen=max_events)
        self._lock = threading.Lock()
        self.started_at = time.time()

    def record(
        self,
        *,
        intent: str,
        model: str | None,
        status: str,
        latency_ms: float,
        first_token_ms: float | None = None,
    ) -> None:
        event = ChatEvent(
            at=time.time(),
            path=path_for_intent(intent),
            intent=intent,
            model=model,
            status=status,
            latency_ms=latency_ms,
            first_token_ms=first_token_ms,
        )

        with self._lock:
            self._events.append(event)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            events = list(self._events)

        paths: dict[str, Any] = {}

        for path in sorted({event.path for event in events}):
            subset = [event for event in events if event.path == path]
            first_tokens = [
                event.first_token_ms
                for event in subset
                if event.first_token_ms is not None
            ]

            paths[path] = {
                "requests": len(subset),
                "errors": sum(1 for e in subset if e.status == "error"),
                "degraded": sum(1 for e in subset if e.status == "degraded"),
                "latency_ms": summarize([e.latency_ms for e in subset]),
                "first_token_ms": summarize(first_tokens),
            }

        total = len(events)

        def share(path: str) -> float | None:
            if not total:
                return None

            return round(
                100 * sum(1 for e in events if e.path == path) / total, 1
            )

        return {
            "window_requests": total,
            "since": self.started_at,
            "note": (
                "Most recent requests since the server started; resets on "
                "restart. Latency covers graph execution, not database "
                "message saving or network transfer."
            ),
            "share_percent": {
                "sql": share("sql"),
                "llm": share("llm"),
                "guardrail": share("guardrail"),
            },
            "error_percent": (
                round(100 * sum(1 for e in events if e.status == "error") / total, 1)
                if total
                else None
            ),
            "by_path": paths,
            "by_intent": dict(Counter(e.intent for e in events)),
            "by_model": dict(Counter(e.model or "none" for e in events)),
        }


chat_metrics = ChatMetrics()
