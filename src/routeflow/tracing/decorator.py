from __future__ import annotations

import functools
from collections.abc import Callable
from typing import TypeVar

from routeflow.tracing.lifecycle import span_scope

F = TypeVar("F", bound=Callable)


def track(func: F) -> F:
    """Wrap a function so every call becomes a span nested under whatever
    span (or trace root) is currently in scope.

    Sync functions only for now — calling this on an `async def` function
    will trace the coroutine's *creation*, not its execution, which is
    wrong. Async support lands in the next commit.
    """
    span_name = func.__name__

    @functools.wraps(func)
    def sync_wrapper(*args: object, **kwargs: object) -> object:
        with span_scope(span_name):
            return func(*args, **kwargs)

    return sync_wrapper  # type: ignore[return-value]
