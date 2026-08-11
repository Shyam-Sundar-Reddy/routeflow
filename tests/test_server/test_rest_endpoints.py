from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI


def test_list_traces_returns_recorded_traces(
    app: FastAPI, do_request: Callable[..., object]
) -> None:
    do_request(app, "GET", "/orders/1")
    do_request(app, "GET", "/orders/2")

    response = do_request(app, "GET", "/__routeflow__/traces")

    assert response.status_code == 200
    traces = response.json()
    assert len(traces) == 2
    # Newest first, per TraceStore.list_traces's documented order.
    assert traces[0]["path"] == "/orders/2"
    assert traces[1]["path"] == "/orders/1"
    assert traces[0]["status"] == "ok"
    assert traces[0]["route_pattern"] == "/orders/{id}"


def test_get_trace_by_id_returns_the_full_trace(
    app: FastAPI, do_request: Callable[..., object]
) -> None:
    do_request(app, "GET", "/orders/42")
    (summary,) = do_request(app, "GET", "/__routeflow__/traces").json()

    response = do_request(app, "GET", f"/__routeflow__/traces/{summary['trace_id']}")

    assert response.status_code == 200
    trace = response.json()
    assert trace["trace_id"] == summary["trace_id"]
    assert trace["path"] == "/orders/42"
    assert trace["method"] == "GET"
    assert "spans" in trace


def test_get_trace_unknown_id_returns_404(
    app: FastAPI, do_request: Callable[..., object]
) -> None:
    response = do_request(app, "GET", "/__routeflow__/traces/does-not-exist")

    assert response.status_code == 404


def test_list_endpoints_returns_aggregated_stats(
    app: FastAPI, do_request: Callable[..., object]
) -> None:
    do_request(app, "GET", "/orders/1")
    do_request(app, "GET", "/orders/2")
    do_request(app, "GET", "/crash")

    response = do_request(app, "GET", "/__routeflow__/endpoints")

    assert response.status_code == 200
    stats = {s["route_pattern"]: s for s in response.json()}
    assert stats["/orders/{id}"]["request_count"] == 2
    assert stats["/orders/{id}"]["error_count"] == 0
    assert stats["/crash"]["request_count"] == 1
    assert stats["/crash"]["error_count"] == 1
