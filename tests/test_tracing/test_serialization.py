from __future__ import annotations

import json

from routeflow.tracing import Trace, track


def test_to_dict_round_trips_a_full_span_tree_through_json(trace: Trace) -> None:
    @track
    def stripe_api_call(amount: int) -> None:
        raise TimeoutError("timed out")

    @track
    def charge_card(amount: int) -> None:
        stripe_api_call(amount)

    @track
    def validate_payment(amount: int) -> bool:
        return amount > 0

    @track
    def handle_order(amount: int) -> None:
        validate_payment(amount)
        charge_card(amount)

    try:
        handle_order(100)
    except TimeoutError as exc:
        trace.record_error(exc)
    trace.finish()

    # The actual round-trip: to_dict() must produce something json.dumps
    # accepts as-is (no custom encoder), and json.loads must hand back
    # the same plain-data shape — this is what the local server (Phase 5)
    # will send over the wire.
    payload = json.loads(json.dumps(trace.to_dict()))

    assert payload["status"] == "error"
    assert payload["error"]["type"] == "TimeoutError"

    spans_by_id = {span["span_id"]: span for span in payload["spans"]}
    assert len(spans_by_id) == 4

    # Rebuild the tree from parent_id, the way a consumer (the flow view)
    # would, and check it matches the call structure exactly.
    roots = [s for s in spans_by_id.values() if s["parent_id"] is None]
    assert [r["name"] for r in roots] == ["handle_order"]

    def children_of(span_id: str) -> list[dict]:
        return sorted(
            (s for s in spans_by_id.values() if s["parent_id"] == span_id),
            key=lambda s: s["start_time"],
        )

    handle_order_span = roots[0]
    assert [c["name"] for c in children_of(handle_order_span["span_id"])] == [
        "validate_payment",
        "charge_card",
    ]

    validate_span, charge_span = children_of(handle_order_span["span_id"])
    assert validate_span["status"] == "ok"
    assert validate_span["args"] == {"amount": "100"}
    assert charge_span["status"] == "error"

    (stripe_span,) = children_of(charge_span["span_id"])
    assert stripe_span["name"] == "stripe_api_call"
    assert stripe_span["error"]["type"] == "TimeoutError"
    assert stripe_span["duration_ms"] is not None
