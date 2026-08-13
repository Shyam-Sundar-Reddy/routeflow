from __future__ import annotations

import asyncio
import inspect

import pytest

from routeflow.tracing import Trace, track


def test_sync_function_produces_a_span(trace: Trace) -> None:
    @track
    def add(a: int, b: int) -> int:
        return a + b

    result = add(2, 3)

    assert result == 5
    (span,) = trace.spans.values()
    assert span.name == "add"
    assert span.status == "ok"
    assert span.duration_ms is not None


def test_async_function_produces_a_span(trace: Trace) -> None:
    @track
    async def fetch(x: int) -> int:
        await asyncio.sleep(0)
        return x * 2

    result = asyncio.run(fetch(21))

    assert result == 42
    (span,) = trace.spans.values()
    assert span.name == "fetch"
    assert span.status == "ok"
    assert span.duration_ms is not None


def test_wraps_preserves_name_and_docstring_sync() -> None:
    @track
    def charge_card(amount: int, currency: str = "usd") -> int:
        """Charge a card for the given amount."""
        return amount

    assert charge_card.__name__ == "charge_card"
    assert charge_card.__doc__ == "Charge a card for the given amount."
    # FastAPI's dependency injection reads this via inspect.signature() —
    # functools.wraps must keep it pointing at the real parameters, not
    # the wrapper's generic (*args, **kwargs).
    params = list(inspect.signature(charge_card).parameters)
    assert params == ["amount", "currency"]


def test_wraps_preserves_name_and_docstring_async() -> None:
    @track
    async def fetch_user(user_id: int) -> int:
        """Fetch a user by id."""
        return user_id

    assert fetch_user.__name__ == "fetch_user"
    assert fetch_user.__doc__ == "Fetch a user by id."
    params = list(inspect.signature(fetch_user).parameters)
    assert params == ["user_id"]


def test_wraps_preserves_name_with_factory_form() -> None:
    @track(name="stripe.charge")
    def charge_card(amount: int) -> int:
        return amount

    # The span gets the override, but the function's own identity is untouched.
    assert charge_card.__name__ == "charge_card"


def test_nested_track_calls_build_the_expected_tree(trace: Trace) -> None:
    @track
    def stripe_api_call(amount: int) -> int:
        return amount

    @track
    def charge_card(amount: int) -> int:
        return stripe_api_call(amount)

    @track
    def validate_payment(amount: int) -> bool:
        return amount > 0

    @track
    def handle_order(amount: int) -> int:
        validate_payment(amount)
        return charge_card(amount)

    handle_order(100)

    (root,) = trace.root_spans()
    assert root.name == "handle_order"

    children = trace.children_of(root.span_id)
    assert [span.name for span in children] == ["validate_payment", "charge_card"]

    charge_span = children[1]
    (grandchild,) = trace.children_of(charge_span.span_id)
    assert grandchild.name == "stripe_api_call"
    assert grandchild.parent_id == charge_span.span_id


def test_sync_exception_is_recorded_and_still_raised(trace: Trace) -> None:
    @track
    def boom() -> None:
        raise ValueError("sync boom")

    with pytest.raises(ValueError, match="sync boom"):
        boom()

    (span,) = trace.spans.values()
    assert span.status == "error"
    assert span.error is not None
    assert span.error.type == "ValueError"
    assert span.error.message == "sync boom"


def test_async_exception_is_recorded_and_still_raised(trace: Trace) -> None:
    @track
    async def aboom() -> None:
        raise ValueError("async boom")

    with pytest.raises(ValueError, match="async boom"):
        asyncio.run(aboom())

    (span,) = trace.spans.values()
    assert span.status == "error"
    assert span.error.type == "ValueError"


def test_exception_marks_every_ancestor_span_errored(trace: Trace) -> None:
    """A failure three calls deep must not look "contained" — every span
    on the path back to the root should show the same failure, matching
    what the flow view renders (error state visible at every ancestor,
    not just the span that actually raised).
    """

    @track
    def stripe_api_call() -> None:
        raise TimeoutError("timed out")

    @track
    def charge_card() -> None:
        stripe_api_call()

    @track
    def handle_order() -> None:
        charge_card()

    with pytest.raises(TimeoutError):
        handle_order()

    assert {span.status for span in trace.spans.values()} == {"error"}
    assert {span.error.type for span in trace.spans.values()} == {"TimeoutError"}


def test_args_are_captured_by_name_with_defaults_applied(trace: Trace) -> None:
    @track
    def charge_card(amount: int, currency: str = "usd") -> int:
        return amount

    charge_card(100)

    (span,) = trace.spans.values()
    assert span.args == {"amount": "100", "currency": "'usd'"}


def test_redact_hook_masks_a_captured_argument(trace: Trace) -> None:
    @track(redact=lambda name, value: "***" if name == "password" else value)
    def login(user: str, password: str) -> bool:
        return True

    login("sam", "hunter2")

    (span,) = trace.spans.values()
    assert span.args["user"] == "'sam'"
    assert span.args["password"] == "'***'"


def test_capture_args_false_skips_capture_entirely(trace: Trace) -> None:
    @track(capture_args=False)
    def login(user: str, password: str) -> bool:
        return True

    login("sam", "hunter2")

    (span,) = trace.spans.values()
    assert span.args == {}
