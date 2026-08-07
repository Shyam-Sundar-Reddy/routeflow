from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


def _new_span_id() -> str:
    return uuid.uuid4().hex


@dataclass
class LogEntry:
    """One log line captured during a span, timestamped relative to the
    same clock as the span itself so it can be placed on the timeline.
    """

    message: str
    timestamp: float = field(default_factory=time.perf_counter)


@dataclass
class Span:
    """A single traced call within a request's execution.

    Represents one `@track`-decorated function call (or the request itself,
    for the root span). Spans nest by `parent_id` to form the call tree that
    RouteFlow renders as a node graph.
    """

    name: str
    trace_id: str
    parent_id: str | None = None
    span_id: str = field(default_factory=_new_span_id)
    # perf_counter, not monotonic: monotonic's resolution varies by platform
    # (~15ms via GetTickCount64 on Windows) and is too coarse for timing
    # individual calls. perf_counter is the stdlib clock meant for this.
    start_time: float = field(default_factory=time.perf_counter)
    end_time: float | None = None
    status: str = "running"
    logs: list[LogEntry] = field(default_factory=list)

    def log(self, message: str) -> None:
        """Record a log line against this span, timestamped now."""
        self.logs.append(LogEntry(message=message))

    @property
    def duration(self) -> float | None:
        """Wall-clock time the call took, in seconds — `None` until closed."""
        if self.end_time is None:
            return None
        return self.end_time - self.start_time

    @property
    def duration_ms(self) -> float | None:
        """`duration` in milliseconds, for display."""
        duration = self.duration
        return None if duration is None else duration * 1000
