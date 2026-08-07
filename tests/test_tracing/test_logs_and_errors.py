from __future__ import annotations

import pytest

from routeflow.tracing import Trace, span_scope


def test_log_is_recorded_on_the_span_it_was_called_on(trace: Trace) -> None:
    with span_scope("stripe_api_call") as span:
        span.log("POST https://api.stripe.com/v1/charges")
        span.log("idempotency_key=ord_7bd201")

    assert [entry.message for entry in span.logs] == [
        "POST https://api.stripe.com/v1/charges",
        "idempotency_key=ord_7bd201",
    ]


def test_logs_on_nested_spans_dont_leak_to_the_parent(trace: Trace) -> None:
    with span_scope("charge_card") as parent:
        parent.log("charging $42.00")
        with span_scope("stripe_api_call") as child:
            child.log("POST https://api.stripe.com/v1/charges")

    assert [e.message for e in parent.logs] == ["charging $42.00"]
    assert [e.message for e in child.logs] == [
        "POST https://api.stripe.com/v1/charges"
    ]


def test_log_entries_are_timestamped_in_call_order(trace: Trace) -> None:
    with span_scope("stripe_api_call") as span:
        span.log("first")
        span.log("second")

    first, second = span.logs
    assert first.timestamp <= second.timestamp


def test_record_error_marks_the_span_and_captures_exception_info(
    trace: Trace,
) -> None:
    with pytest.raises(TimeoutError):
        with span_scope("stripe_api_call") as span:
            raise TimeoutError("stripe_api_call timed out after 5000ms")

    assert span.status == "error"
    assert span.error is not None
    assert span.error.type == "TimeoutError"
    assert span.error.message == "stripe_api_call timed out after 5000ms"
    assert "TimeoutError" in span.error.traceback


def test_error_propagates_to_every_enclosing_span(trace: Trace) -> None:
    # Mirrors the Flow tab mockup: a failure in stripe_api_call marks
    # charge_card and handle_order as errored too, since they didn't
    # complete successfully either.
    with pytest.raises(TimeoutError):
        with span_scope("handle_order") as root:
            with span_scope("charge_card") as charge:
                with span_scope("stripe_api_call") as stripe:
                    raise TimeoutError("timed out")

    assert stripe.status == "error"
    assert charge.status == "error"
    assert root.status == "error"


def test_sibling_of_a_failed_span_is_unaffected(trace: Trace) -> None:
    with pytest.raises(TimeoutError):
        with span_scope("handle_order"):
            with span_scope("validate_payment") as sibling:
                pass
            with span_scope("charge_card"):
                raise TimeoutError("timed out")

    assert sibling.status == "ok"
    assert sibling.error is None


def test_exception_is_re_raised_unchanged(trace: Trace) -> None:
    original = TimeoutError("stripe_api_call timed out after 5000ms")
    with pytest.raises(TimeoutError) as exc_info:
        with span_scope("stripe_api_call"):
            raise original

    # span_scope must never alter what the wrapped code raises.
    assert exc_info.value is original


def test_finished_trace_status_reflects_a_span_error(trace: Trace) -> None:
    with pytest.raises(TimeoutError):
        with span_scope("handle_order"):
            with span_scope("stripe_api_call"):
                raise TimeoutError("timed out")

    trace.finish()
    assert trace.status == "error"


def test_finished_trace_status_is_ok_with_no_errors(trace: Trace) -> None:
    with span_scope("handle_order"):
        with span_scope("validate_payment"):
            pass

    trace.finish()
    assert trace.status == "ok"
