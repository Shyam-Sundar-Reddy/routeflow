from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from routeflow.tracing.context import (
    get_current_span,
    get_current_trace,
    reset_current_span,
    set_current_span,
)
from routeflow.tracing.span import Span


def open_span(name: str) -> Span:
    """Start a new span under whatever trace/span is currently in scope.

    Requires an active trace (set by the request middleware) — raises if
    called outside of one, since a span with nowhere to attach is a bug in
    the caller, not something to silently ignore.
    """
    trace = get_current_trace()
    if trace is None:
        raise RuntimeError(
            f"open_span({name!r}) called with no active trace. "
            "Traced calls must happen inside a request handled by "
            "RouteFlow's middleware."
        )

    parent = get_current_span()
    span = Span(
        name=name,
        trace_id=trace.trace_id,
        parent_id=parent.span_id if parent else None,
    )
    trace.spans[span.span_id] = span
    return span


def close_span(span: Span) -> None:
    """Mark a span finished by recording its end time."""
    span.end_time = time.monotonic()


@contextmanager
def span_scope(name: str) -> Iterator[Span]:
    """Open a span, make it the current span for the duration of the block,
    and close it on exit — success or failure alike.
    """
    span = open_span(name)
    token = set_current_span(span)
    try:
        yield span
    finally:
        close_span(span)
        reset_current_span(token)
