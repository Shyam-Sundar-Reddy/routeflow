from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import TypeVar, overload

from routeflow.tracing.lifecycle import span_scope

F = TypeVar("F", bound=Callable)

Redactor = Callable[[str, object], object]

_MAX_REPR_LEN = 200


def _safe_repr(value: object) -> str:
    """`repr(value)`, but never lets a broken `__repr__` break tracing."""
    try:
        text = repr(value)
    except Exception:  # noqa: BLE001 - a user's __repr__ can raise anything
        return "<unrepr-able>"
    if len(text) > _MAX_REPR_LEN:
        text = text[: _MAX_REPR_LEN - 1] + "…"
    return text


def _make_capture(
    sig: inspect.Signature, redact: Redactor | None
) -> Callable[[tuple, dict], dict[str, str]]:
    """Build the per-call argument capturer for one wrapped function.

    Binds `(*args, **kwargs)` to parameter names via the function's own
    signature, so the span records `amount=100` rather than an unlabeled
    positional list. Values are optionally passed through `redact(name,
    value)` — e.g. to mask a password — before being stringified with
    `_safe_repr`; the raw value itself is never retained on the span.
    """

    def capture(args: tuple, kwargs: dict) -> dict[str, str]:
        try:
            bound = sig.bind_partial(*args, **kwargs)
        except TypeError:
            # Call doesn't match the signature (e.g. called incorrectly) —
            # let the real call raise that error; just skip capture here.
            return {}
        bound.apply_defaults()
        captured: dict[str, str] = {}
        for param_name, value in bound.arguments.items():
            if redact is not None:
                value = redact(param_name, value)
            captured[param_name] = _safe_repr(value)
        return captured

    return capture


@overload
def track(func: F) -> F: ...
@overload
def track(
    func: None = None,
    *,
    name: str | None = None,
    redact: Redactor | None = None,
) -> Callable[[F], F]: ...


def track(
    func: F | None = None,
    *,
    name: str | None = None,
    redact: Redactor | None = None,
) -> F | Callable[[F], F]:
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

    Call arguments are captured on the span by name (bound via the
    function's own signature) unless `redact` maps a given
    `(param_name, value)` to something safe to store instead — e.g.
    `redact=lambda name, value: "***" if name == "password" else value`.
    """

    def decorator(func: F) -> F:
        span_name = name or func.__name__
        capture = _make_capture(inspect.signature(func), redact)

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: object, **kwargs: object) -> object:
                with span_scope(span_name) as span:
                    span.args = capture(args, kwargs)
                    return await func(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: object, **kwargs: object) -> object:
            with span_scope(span_name) as span:
                span.args = capture(args, kwargs)
                return func(*args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    if func is not None:
        # Bare @track — func is the thing being decorated.
        return decorator(func)
    # @track(name=..., redact=...) — return the factory to apply.
    return decorator
