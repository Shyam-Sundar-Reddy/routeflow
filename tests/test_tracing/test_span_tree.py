from __future__ import annotations

from routeflow.tracing import Trace, span_scope


def test_root_span_has_no_parent(trace: Trace) -> None:
    with span_scope("handle_order") as root:
        pass

    assert root.parent_id is None
    assert trace.root_spans() == [root]


def test_nested_span_is_child_of_enclosing_span(trace: Trace) -> None:
    with span_scope("handle_order") as root:
        with span_scope("validate_payment") as child:
            pass

    assert child.parent_id == root.span_id
    assert trace.children_of(root.span_id) == [child]


def test_sibling_spans_share_one_parent_in_call_order(trace: Trace) -> None:
    with span_scope("handle_order") as root:
        with span_scope("validate_payment") as first:
            pass
        with span_scope("charge_card") as second:
            pass

    children = trace.children_of(root.span_id)
    assert children == [first, second]
    assert all(child.parent_id == root.span_id for child in children)


def test_three_level_tree_matches_the_call_structure(trace: Trace) -> None:
    # Mirrors the handle_order -> charge_card -> stripe_api_call shape
    # from the Flow tab mockup.
    with span_scope("handle_order") as root:
        with span_scope("validate_payment"):
            pass
        with span_scope("charge_card") as charge:
            with span_scope("stripe_api_call") as stripe:
                pass

    assert trace.root_spans() == [root]
    assert [s.name for s in trace.children_of(root.span_id)] == [
        "validate_payment",
        "charge_card",
    ]
    assert trace.children_of(charge.span_id) == [stripe]
    assert trace.children_of(stripe.span_id) == []  # leaf span, no children


def test_span_scope_restores_previous_current_span_after_exit(
    trace: Trace,
) -> None:
    from routeflow.tracing.context import get_current_span

    with span_scope("handle_order") as root:
        assert get_current_span() is root
        with span_scope("validate_payment") as child:
            assert get_current_span() is child
        # back to root once the inner block exits
        assert get_current_span() is root
    # back to nothing once the outer block exits
    assert get_current_span() is None
