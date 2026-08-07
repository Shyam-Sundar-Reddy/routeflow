from __future__ import annotations

import contextvars

from routeflow.tracing.span import Span
from routeflow.tracing.trace import Trace

# Each holds the trace/span "in scope" for whatever coroutine or thread is
# currently executing. Isolated per asyncio task (copied on task creation)
# and per thread — never a shared global, so concurrent requests can't
# see or overwrite each other's context.
_current_trace: contextvars.ContextVar[Trace | None] = contextvars.ContextVar(
    "routeflow_current_trace", default=None
)
_current_span: contextvars.ContextVar[Span | None] = contextvars.ContextVar(
    "routeflow_current_span", default=None
)


def get_current_trace() -> Trace | None:
    """The trace for whatever request is currently executing, if any."""
    return _current_trace.get()


def set_current_trace(trace: Trace | None) -> contextvars.Token:
    """Set the current trace; returns a token for `reset_current_trace`."""
    return _current_trace.set(trace)


def reset_current_trace(token: contextvars.Token) -> None:
    _current_trace.reset(token)


def get_current_span() -> Span | None:
    """The span whose call is currently executing, if any.

    This is the "innermost" open span — the natural parent for whatever
    `@track`-decorated call happens next.
    """
    return _current_span.get()


def set_current_span(span: Span | None) -> contextvars.Token:
    """Set the current span; returns a token for `reset_current_span`."""
    return _current_span.set(span)


def reset_current_span(token: contextvars.Token) -> None:
    _current_span.reset(token)
