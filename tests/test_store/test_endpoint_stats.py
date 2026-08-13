from __future__ import annotations

from collections.abc import Callable

from routeflow.store import UNMATCHED_ROUTE, TraceStore
from routeflow.tracing import Trace


def test_stats_computed_against_a_known_fixture(make_trace: Callable[..., Trace]) -> None:
    """Durations chosen so p95 is hand-calculable via the standard
    linear-interpolation formula, not just re-derived from the same code
    under test:

        n=5, k=(5-1)*0.95=3.8 -> between the 4th and 5th sorted values
        ordered=[10,20,30,40,50]
        p95 = 40*(4-3.8) + 50*(3.8-3) = 8 + 40 = 48.0
    """
    store = TraceStore()
    durations = [10.0, 20.0, 30.0, 40.0, 50.0]
    for i, duration in enumerate(durations):
        store.add(
            make_trace(
                path=f"/orders/{i}",
                route_pattern="/orders/{id}",
                status="error" if duration == 30.0 else "ok",
                duration_ms=duration,
            )
        )

    (stats,) = store.endpoint_stats()

    assert stats.method == "GET"
    assert stats.route_pattern == "/orders/{id}"
    assert stats.request_count == 5
    assert stats.error_count == 1
    assert stats.error_rate == 0.2
    assert stats.p95_duration_ms is not None
    assert abs(stats.p95_duration_ms - 48.0) < 1e-9


def test_stats_group_separately_by_method_and_pattern(
    make_trace: Callable[..., Trace],
) -> None:
    store = TraceStore()
    store.add(make_trace(method="GET", route_pattern="/orders/{id}"))
    store.add(make_trace(method="GET", route_pattern="/orders/{id}"))
    store.add(make_trace(method="DELETE", route_pattern="/orders/{id}"))
    store.add(make_trace(method="GET", route_pattern="/health"))

    stats = {(s.method, s.route_pattern): s for s in store.endpoint_stats()}

    assert stats[("GET", "/orders/{id}")].request_count == 2
    assert stats[("DELETE", "/orders/{id}")].request_count == 1
    assert stats[("GET", "/health")].request_count == 1


def test_unmatched_routes_group_under_a_single_bucket(
    make_trace: Callable[..., Trace],
) -> None:
    store = TraceStore()
    store.add(make_trace(path="/nope", route_pattern=None))
    store.add(make_trace(path="/also-nope", route_pattern=None))

    (stats,) = store.endpoint_stats()

    assert stats.route_pattern == UNMATCHED_ROUTE
    assert stats.request_count == 2


def test_stats_sorted_busiest_first(make_trace: Callable[..., Trace]) -> None:
    store = TraceStore()
    store.add(make_trace(method="GET", route_pattern="/health"))
    for _ in range(3):
        store.add(make_trace(method="GET", route_pattern="/orders/{id}"))

    stats = store.endpoint_stats()

    assert [s.route_pattern for s in stats] == ["/orders/{id}", "/health"]


def test_p95_is_none_when_no_traces_have_finished(
    make_trace: Callable[..., Trace],
) -> None:
    store = TraceStore()
    store.add(make_trace(route_pattern="/orders/{id}", duration_ms=None))

    (stats,) = store.endpoint_stats()

    assert stats.request_count == 1
    assert stats.p95_duration_ms is None
