from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass

from routeflow.tracing import Trace

DEFAULT_MAX_TRACES = 500

# The bucket unmatched requests (a 404 — see the middleware's
# _route_pattern) group under, since None isn't a usable dict/display key
# and "every 404 gets its own row" would be useless in the flow view.
UNMATCHED_ROUTE = "unmatched"


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile — the standard definition (same
    one `numpy.percentile`'s default uses), not a stdlib one-liner:
    `statistics.quantiles` refuses a single-value sample, which a
    lightly-used endpoint will very often be.
    """
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * pct
    lower, upper = math.floor(k), math.ceil(k)
    if lower == upper:
        return ordered[int(k)]
    return ordered[lower] * (upper - k) + ordered[upper] * (k - lower)


@dataclass
class EndpointStats:
    """Aggregate numbers for one (method, route pattern) pair — what the
    flow view's endpoint sidebar lists instead of raw traces.
    """

    method: str
    route_pattern: str
    request_count: int
    error_count: int
    error_rate: float
    p95_duration_ms: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "route_pattern": self.route_pattern,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "error_rate": self.error_rate,
            "p95_duration_ms": self.p95_duration_ms,
        }


class TraceStore:
    """Holds the most recently finished traces, in memory, bounded.

    Nothing here is persisted to disk — RouteFlow is dev-only tooling;
    restarting the app is expected to lose history, same as restarting
    any other dev server loses its in-memory state. `maxlen` is what
    keeps a long-running dev session from growing this without bound: once
    full, appending drops the oldest trace automatically (that's
    `deque(maxlen=...)`'s behavior, not logic this class has to implement).

    A single asyncio event loop wouldn't need locking here — coroutines
    only switch at an `await`, so a plain `deque.append` can't be
    interrupted mid-operation. But FastAPI runs plain `def` route
    handlers in a threadpool, so a write here can genuinely happen on a
    different OS thread at the same instant as another. The lock is cheap
    insurance for that case, not a sign anything here is slow.
    """

    def __init__(self, maxlen: int = DEFAULT_MAX_TRACES) -> None:
        self._traces: deque[Trace] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def add(self, trace: Trace) -> None:
        """Record a finished trace, evicting the oldest one if full."""
        with self._lock:
            self._traces.append(trace)

    def list_traces(self, *, route_pattern: str | None = None) -> list[Trace]:
        """Stored traces, newest first — the order a "recent traces"
        list in the flow view wants them in, opposite of insertion order.

        A snapshot, not a live view — copied out while holding the lock
        so a caller iterating the result can't race a concurrent write
        mutating the same deque underneath it.

        `route_pattern`, when given, filters to traces matching exactly
        (e.g. `"/orders/{id}"`) — for listing "recent traces for this
        endpoint" the way the flow view groups them.
        """
        with self._lock:
            snapshot = list(self._traces)
        snapshot.reverse()
        if route_pattern is not None:
            snapshot = [t for t in snapshot if t.route_pattern == route_pattern]
        return snapshot

    def get(self, trace_id: str) -> Trace | None:
        """A single trace by id, or `None` if it's not stored — either
        it never existed, or it aged out of the ring buffer.
        """
        with self._lock:
            for trace in self._traces:
                if trace.trace_id == trace_id:
                    return trace
        return None

    def endpoint_stats(self) -> list[EndpointStats]:
        """One `EndpointStats` per (method, route pattern) currently
        represented in the store, busiest first. Computed fresh from
        whatever's in the ring buffer right now — there's no separate
        running total, so a stat's window is implicitly "however far
        back the buffer currently reaches."
        """
        with self._lock:
            snapshot = list(self._traces)

        groups: dict[tuple[str, str], list[Trace]] = {}
        for trace in snapshot:
            key = (trace.method, trace.route_pattern or UNMATCHED_ROUTE)
            groups.setdefault(key, []).append(trace)

        stats = []
        for (method, pattern), traces in groups.items():
            durations = [
                trace.duration * 1000 for trace in traces if trace.duration is not None
            ]
            error_count = sum(1 for trace in traces if trace.status == "error")
            stats.append(
                EndpointStats(
                    method=method,
                    route_pattern=pattern,
                    request_count=len(traces),
                    error_count=error_count,
                    error_rate=error_count / len(traces),
                    p95_duration_ms=_percentile(durations, 0.95) if durations else None,
                )
            )
        return sorted(stats, key=lambda s: s.request_count, reverse=True)

    def __len__(self) -> int:
        with self._lock:
            return len(self._traces)
