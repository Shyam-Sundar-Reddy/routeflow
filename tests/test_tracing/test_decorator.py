from __future__ import annotations

import asyncio
import inspect

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
