from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


def _new_span_id() -> str:
    return uuid.uuid4().hex


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
    start_time: float = field(default_factory=time.monotonic)
    end_time: float | None = None
    status: str = "running"
