from __future__ import annotations

import functools
import inspect
import warnings
from collections.abc import Callable, Iterable
from types import ModuleType
from typing import TypeVar, overload

from routeflow.tracing.lifecycle import span_scope

F = TypeVar("F", bound=Callable)

Redactor = Callable[[str, object], object]

_MAX_REPR_LEN = 200


def mask(*field_names: str, replacement: str = "***") -> Redactor:
    """Build a `redact=` callable that masks specific argument names by
    exact match:

        @track(redact=mask("password", "token"))
        def login(username: str, password: str) -> bool: ...

    Saves writing the same few-line lambda by hand — nothing more. Still
    opt-in by name, not by guessing which arguments "look sensitive": you
    name exactly what gets masked, same as writing the lambda yourself
    would require. Auto-redacting anything whose name merely *contains*
    "password"/"token"/etc. would be a different, riskier feature (false
    negatives on anything not guessed, false positives on legitimate
    args) — not what this does.
    """
    names = set(field_names)

    def redact(name: str, value: object) -> object:
        return replacement if name in names else value

    return redact


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
    capture_args: bool = True,
) -> Callable[[F], F]: ...


def track(
    func: F | None = None,
    *,
    name: str | None = None,
    redact: Redactor | None = None,
    capture_args: bool = True,
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

    Set `capture_args=False` to skip argument capture for this function
    entirely — for a function whose arguments shouldn't be written to a
    trace at all (a raw credential, a full request body), not just
    individually masked.

    Generator and async-generator functions (`yield`) are not supported
    yet: calling `func(*args, **kwargs)` on one only *creates* the
    generator, it doesn't run the body, so the span the current wrappers
    open would close almost instantly — before a single item is produced —
    and record a near-zero, meaningless duration. Decorating one issues a
    `RuntimeWarning` for now rather than failing outright, since the
    function still works, just without accurate tracing. Proper support
    (a wrapper that stays open across iteration) is tracked for a later
    phase.
    """

    def decorator(func: F) -> F:
        if inspect.isgeneratorfunction(func) or inspect.isasyncgenfunction(func):
            warnings.warn(
                f"@track on {func.__qualname__!r}: generator/async-generator "
                "functions aren't properly supported yet — the recorded span "
                "will close as soon as the generator object is created, not "
                "when it's actually consumed, so its duration will be "
                "meaningless.",
                RuntimeWarning,
                stacklevel=2,
            )

        span_name = name or func.__name__
        capture = (
            _make_capture(inspect.signature(func), redact)
            if capture_args
            else lambda args, kwargs: {}
        )

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: object, **kwargs: object) -> object:
                # span is None when there's no active trace (RouteFlow
                # disabled) - span_scope's own true-no-op case; skip
                # capture rather than crash on None.args.
                with span_scope(span_name) as span:
                    if span is not None:
                        span.args = capture(args, kwargs)
                    return await func(*args, **kwargs)

            # Lets track_module() (and anything else) tell "already
            # @track-ed" apart from "not yet" - functools.wraps doesn't
            # copy this from the original, since the original was never
            # tracked itself.
            async_wrapper.__routeflow_tracked__ = True  # type: ignore[attr-defined]
            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: object, **kwargs: object) -> object:
            with span_scope(span_name) as span:
                if span is not None:
                    span.args = capture(args, kwargs)
                return func(*args, **kwargs)

        sync_wrapper.__routeflow_tracked__ = True  # type: ignore[attr-defined]
        return sync_wrapper  # type: ignore[return-value]

    if func is not None:
        # Bare @track — func is the thing being decorated.
        return decorator(func)
    # @track(name=..., redact=...) — return the factory to apply.
    return decorator


def track_module(
    module: ModuleType,
    *,
    exclude: Iterable[str] = (),
    redact: Redactor | None = None,
    capture_args: bool = True,
) -> list[str]:
    """Apply `@track` to every function *defined in* `module`, in place.

        from routeflow.tracing import track_module
        import myapp.services.orders as orders

        track_module(orders, exclude={"_internal_helper"})

    Deliberately *not* a global `auto_trace=True` switch — that would
    undermine the whole point of `redact=`/`capture_args=False`: those
    only work because a human looked at a specific function and decided
    what's safe to capture. Auto-tracing an entire app means capturing
    arguments for functions nobody ever reviewed for "does this take a
    password" — the same silent-leak risk `RouteFlow(app)`'s docstring
    warns about for the whole app, just per-function instead of per-app.
    This is the scoped middle ground instead: bulk convenience for
    onboarding an existing module, but still a deliberate, reviewable
    call site — `git diff` shows exactly which module opted in, and
    `exclude=`/a manual `@track(...)` beforehand still let individual
    functions be handled differently.

    Two things are skipped automatically, not just `exclude`:

    - Anything not a plain function *defined in this module* — a class,
      a re-exported name imported from elsewhere (`obj.__module__` won't
      match `module.__name__`), anything already wrapped by an earlier
      `track`/`track_module` call (checked via the marker `track` sets,
      not by re-inspecting behavior).
    - Scoped to top-level functions only — methods aren't walked here.
      Bound/unbound methods, `__init__`, and inherited methods are enough
      of a separate problem that they're deliberately left out rather
      than guessed at.

    Returns the names actually wrapped, so a caller can log or assert
    what happened — bulk shouldn't mean invisible.
    """
    excluded = set(exclude)
    wrapped_names: list[str] = []

    for attr_name, obj in list(vars(module).items()):
        if attr_name in excluded:
            continue
        if not inspect.isfunction(obj):
            continue
        if getattr(obj, "__module__", None) != module.__name__:
            continue  # imported from elsewhere, not defined here
        if getattr(obj, "__routeflow_tracked__", False):
            continue  # already @track-ed, manually or by an earlier call

        setattr(module, attr_name, track(obj, redact=redact, capture_args=capture_args))
        wrapped_names.append(attr_name)

    return wrapped_names
