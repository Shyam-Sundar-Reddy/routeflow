from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from routeflow.tracing.span import Span


def _new_trace_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Trace:
    """Everything captured for a single request.

    Holds the request's identifying info plus every `Span` recorded during
    it, keyed by span id. Parent/child structure lives on the spans
    themselves (`Span.parent_id`); `Trace` is just the flat collection scoped
    to one request.
    """

    method: str
    path: str
    trace_id: str = field(default_factory=_new_trace_id)
    route_pattern: str | None = None
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float | None = None
    status: str = "running"
    spans: dict[str, Span] = field(default_factory=dict)
