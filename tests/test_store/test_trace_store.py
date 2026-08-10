from __future__ import annotations

from collections.abc import Callable

from routeflow.store import TraceStore
from routeflow.tracing import Trace


def test_buffer_evicts_the_oldest_trace_once_full(
    make_trace: Callable[..., Trace],
) -> None:
    store = TraceStore(maxlen=3)
    traces = [make_trace(path=f"/orders/{i}") for i in range(5)]

    for trace in traces:
        store.add(trace)

    assert len(store) == 3
    # The first two (oldest) should be gone; the last three remain.
    remaining_ids = {t.trace_id for t in store.list_traces()}
    assert remaining_ids == {traces[2].trace_id, traces[3].trace_id, traces[4].trace_id}


def test_list_traces_returns_newest_first(make_trace: Callable[..., Trace]) -> None:
    store = TraceStore()
    traces = [make_trace(path=f"/orders/{i}") for i in range(3)]
    for trace in traces:
        store.add(trace)

    assert [t.trace_id for t in store.list_traces()] == [
        t.trace_id for t in reversed(traces)
    ]


def test_list_traces_filters_by_route_pattern(make_trace: Callable[..., Trace]) -> None:
    store = TraceStore()
    store.add(make_trace(path="/orders/1", route_pattern="/orders/{id}"))
    store.add(make_trace(path="/health", route_pattern="/health"))
    store.add(make_trace(path="/orders/2", route_pattern="/orders/{id}"))

    filtered = store.list_traces(route_pattern="/orders/{id}")

    assert {t.path for t in filtered} == {"/orders/1", "/orders/2"}


def test_get_returns_a_trace_by_id_or_none(make_trace: Callable[..., Trace]) -> None:
    store = TraceStore()
    trace = make_trace()
    store.add(trace)

    assert store.get(trace.trace_id) is trace
    assert store.get("does-not-exist") is None


def test_get_returns_none_for_an_evicted_trace(make_trace: Callable[..., Trace]) -> None:
    store = TraceStore(maxlen=1)
    evicted = make_trace(path="/orders/1")
    store.add(evicted)
    store.add(make_trace(path="/orders/2"))

    assert store.get(evicted.trace_id) is None
