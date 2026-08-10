from __future__ import annotations

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
    """

    def __init__(self, maxlen: int = DEFAULT_MAX_TRACES) -> None:
        self._traces: deque[Trace] = deque(maxlen=maxlen)

    def add(self, trace: Trace) -> None:
        """Record a finished trace, evicting the oldest one if full."""
        self._traces.append(trace)

    def __len__(self) -> int:
        return len(self._traces)
