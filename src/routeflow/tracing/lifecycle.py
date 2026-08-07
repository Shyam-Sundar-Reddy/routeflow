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
    """Mark a span finished: record its end time and, unless something
    already flagged it otherwise (e.g. `record_error`), derive a final
    "ok" status from having completed without one.
    """
    span.end_time = time.perf_counter()
    if span.status == "running":
        span.status = "ok"


@contextmanager
def span_scope(name: str) -> Iterator[Span]:
    """Open a span, make it the current span for the duration of the block,
    and close it on exit — success or failure alike.

    An exception raised inside the block is recorded on the span (so it
    doesn't get silently marked "ok" by close_span) and always re-raised
    unchanged — this must never alter what the wrapped code does, only
    observe it.
    """
    span = open_span(name)
    token = set_current_span(span)
    try:
        yield span
    except BaseException as exc:
        span.record_error(exc)
        raise
    finally:
        close_span(span)
        reset_current_span(token)
