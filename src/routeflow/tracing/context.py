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

# A shared, never-registered-on-any-trace placeholder — get_current_span()
# hands this back instead of None when there's no active trace at all
# (RouteFlow disabled). It exists purely so user code that reasonably
# calls get_current_span().log(...) inside a @track-ed function (the same
# pattern this project's own examples use) is a harmless no-op rather
# than an AttributeError on None, the moment tracing happens to be off.
# Never read back by anything - not stored on a Trace, not serialized.
_DISABLED_SPAN = Span(name="<routeflow-disabled>", trace_id="<none>")


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

    Returns the shared `_DISABLED_SPAN` placeholder, not `None`, when
    there's no active trace at all (RouteFlow disabled) — see its
    docstring for why. Still returns real `None` for the *other* case
    that also has no current span: a trace is active, but nothing has
    opened a span yet (i.e. before the first `@track` call in a
    request). That distinction matters — `open_span` relies on real
    `None` here to correctly mark a call as a trace's root span, not a
    child of some shared placeholder.
    """
    span = _current_span.get()
    if span is not None:
        return span
    if _current_trace.get() is None:
        return _DISABLED_SPAN
    return None


def set_current_span(span: Span | None) -> contextvars.Token:
    """Set the current span; returns a token for `reset_current_span`."""
    return _current_span.set(span)


def reset_current_span(token: contextvars.Token) -> None:
    _current_span.reset(token)
