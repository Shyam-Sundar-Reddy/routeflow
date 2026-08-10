from __future__ import annotations

import threading
from collections import deque

from routeflow.tracing import Trace

DEFAULT_MAX_TRACES = 500


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

    def __len__(self) -> int:
        with self._lock:
            return len(self._traces)
