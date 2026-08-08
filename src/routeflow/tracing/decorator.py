from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import TypeVar, overload

from routeflow.tracing.lifecycle import span_scope

F = TypeVar("F", bound=Callable)


@overload
def track(func: F) -> F: ...
@overload
def track(func: None = None, *, name: str | None = None) -> Callable[[F], F]: ...


def track(func: F | None = None, *, name: str | None = None) -> F | Callable[[F], F]:
    """Wrap a function so every call becomes a span nested under whatever
    span (or trace root) is currently in scope.

    Usable bare, or as a decorator factory with an explicit span name:

        @track
        def charge_card(...): ...

        @track(name="stripe.charge")
        def charge_card(...): ...

    Works on both `def` and `async def` functions. Which wrapper gets used
    is decided once, at decoration time (`inspect.iscoroutinefunction`) —
    not on every call — so there's no per-call dispatch cost.

    `span_scope` itself does no I/O, so a plain `with` (not `async with`)
    is correct even inside the async wrapper.

    If the wrapped call raises, the exception is recorded on its span
    (status becomes "error", with type/message/traceback captured) and
    then always re-raised unchanged — @track only observes a call, it
    never alters what the call does or returns.
    """

    def decorator(func: F) -> F:
        span_name = name or func.__name__

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

    if func is not None:
        # Bare @track — func is the thing being decorated.
        return decorator(func)
    # @track(name=...) — return the factory to be applied to the function.
    return decorator
