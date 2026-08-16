from __future__ import annotations

from pathlib import Path

import pytest

from routeflow.tracing import Trace, track_module

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def orders_module(monkeypatch: pytest.MonkeyPatch):
    """A real, importable module (not a fixture function standing in for
    one) - track_module() cares about genuine module identity
    (`func.__module__`), which can't be faked with an inline namespace.
    A fresh import each test, so track_module's own mutations (it
    replaces functions in place via setattr) never leak between tests.
    """
    import sys

    monkeypatch.syspath_prepend(str(FIXTURES_DIR))
    for name in list(sys.modules):
        if name == "track_module_pkg" or name.startswith("track_module_pkg."):
            del sys.modules[name]

    from track_module_pkg import orders

    return orders


def test_wraps_only_functions_defined_in_the_module(orders_module) -> None:
    wrapped = track_module(orders_module)

    assert set(wrapped) == {"validate", "charge", "_internal_helper"}


def test_does_not_wrap_names_imported_from_elsewhere(orders_module) -> None:
    track_module(orders_module)

    assert not getattr(orders_module.shared_helper, "__routeflow_tracked__", False)


def test_does_not_wrap_classes(orders_module) -> None:
    track_module(orders_module)

    assert not hasattr(orders_module.Foo, "__routeflow_tracked__")


def test_exclude_skips_named_functions(orders_module) -> None:
    wrapped = track_module(orders_module, exclude={"_internal_helper"})

    assert "_internal_helper" not in wrapped
    assert not getattr(orders_module._internal_helper, "__routeflow_tracked__", False)


def test_skips_a_function_already_tracked_by_hand(orders_module) -> None:
    wrapped = track_module(orders_module)

    # already_tracked has its own @track in the fixture file - must not
    # be re-wrapped (double-wrapping would nest an extra nameless span
    # around the real one on every call).
    assert "already_tracked" not in wrapped


def test_second_call_wraps_nothing_new(orders_module) -> None:
    first = track_module(orders_module)
    second = track_module(orders_module)

    assert set(first) == {"validate", "charge", "_internal_helper"}
    assert second == []


def test_wrapped_function_actually_produces_a_span(orders_module, trace: Trace) -> None:
    track_module(orders_module)

    result = orders_module.charge(21)

    assert result == 42  # shared_helper(21) * 2, still called through fine
    (span,) = trace.spans.values()
    assert span.name == "charge"
    assert span.status == "ok"


def test_redact_and_capture_args_pass_through_to_every_wrapped_function(
    orders_module, trace: Trace
) -> None:
    track_module(orders_module, redact=lambda name, value: "***" if name == "amount" else value)

    orders_module.validate(100)

    (span,) = trace.spans.values()
    assert span.args["amount"] == "'***'"
