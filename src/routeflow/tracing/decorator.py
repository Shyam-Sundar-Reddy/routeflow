from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import TypeVar

from routeflow.tracing.lifecycle import span_scope

F = TypeVar("F", bound=Callable)


def track(func: F) -> F:
    """Wrap a function so every call becomes a span nested under whatever
    span (or trace root) is currently in scope.

    Works on both `def` and `async def` functions. Which wrapper gets used
    is decided once, at decoration time (`inspect.iscoroutinefunction`) —
    not on every call — so there's no per-call dispatch cost.

    `span_scope` itself does no I/O, so a plain `with` (not `async with`)
    is correct even inside the async wrapper.
    """
    span_name = func.__name__

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: object, **kwargs: object) -> object:
            with span_scope(span_name):
                return await func(*args, **kwargs)

        return async_wrapper  # type: ignore[return-value]

    @functools.wraps(func)
    def sync_wrapper(*args: object, **kwargs: object) -> object:
        with span_scope(span_name):
            return func(*args, **kwargs)

    return sync_wrapper  # type: ignore[return-value]
