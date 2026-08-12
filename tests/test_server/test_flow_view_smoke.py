from __future__ import annotations

import re
from collections.abc import Callable

from fastapi import FastAPI

from routeflow import RouteFlow
from routeflow.tracing import track

# No browser/Playwright dependency here — this is a data-and-wiring smoke
# test, not a rendered-pixels test. It proves every contract the frontend
# actually depends on: the static files are served and cross-reference
# each other correctly, every DOM id app.js looks up by id genuinely
# exists in index.html, and the REST responses have the exact shape
# app.js reads fields off of. What it can't prove is that a browser
# paints the result correctly — that's a real gap, and a Playwright-based
# render test is the natural next step if/when a browser-automation
# dependency becomes acceptable for this project.


@track
def stripe_api_call(amount: int) -> None:
    raise TimeoutError("timed out")


@track
def charge_card(amount: int) -> None:
    stripe_api_call(amount)


@track
def validate_payment(amount: int) -> bool:
    return amount > 0


def _build_traced_app() -> FastAPI:
    fastapi_app = FastAPI()

    @fastapi_app.post("/orders")
    def create_order(amount: int) -> dict[str, int]:
        validate_payment(amount)
        charge_card(amount)
        return {"amount": amount}

    RouteFlow(fastapi_app)
    return fastapi_app


def test_flow_view_serves_and_renders_a_real_traced_request(
    do_request: Callable[..., object],
) -> None:
    app = _build_traced_app()

    # A real request through the real middleware/decorator stack, deep
    # enough to exercise nesting, args, and an error - the same scenario
    # the node graph, detail panel, and timeline strip are built around.
    response = do_request(
        app, "POST", "/orders?amount=100", raise_app_exceptions=False
    )
    assert response.status_code == 500

    # --- Static files are served and cross-reference each other ---
    index_response = do_request(app, "GET", "/__routeflow__/app/")
    assert index_response.status_code == 200
    index_html = index_response.text
    assert 'src="app.js"' in index_html
    assert 'href="app.css"' in index_html

    js_response = do_request(app, "GET", "/__routeflow__/app/app.js")
    assert js_response.status_code == 200
    app_js = js_response.text

    css_response = do_request(app, "GET", "/__routeflow__/app/app.css")
    assert css_response.status_code == 200

    # --- Every element id app.js looks up must exist in index.html ---
    # A renamed id in either file, with the other not updated, is exactly
    # the class of bug this catches - and the kind that's otherwise
    # invisible until someone opens the page and something silently does
    # nothing.
    referenced_ids = set(re.findall(r'getElementById\("([^"]+)"\)', app_js))
    assert referenced_ids, "expected app.js to reference at least one element id"
    for element_id in referenced_ids:
        assert f'id="{element_id}"' in index_html, (
            f"app.js references #{element_id}, but index.html has no such id"
        )

    # --- REST responses have the shape app.js's renderers read ---
    endpoints = do_request(app, "GET", "/__routeflow__/endpoints").json()
    (endpoint,) = endpoints
    for field in (
        "method",
        "route_pattern",
        "request_count",
        "error_count",
        "error_rate",
        "p95_duration_ms",
    ):
        assert field in endpoint

    traces = do_request(
        app, "GET", f"/__routeflow__/traces?route_pattern={endpoint['route_pattern']}"
    ).json()
    (trace_summary,) = traces

    trace = do_request(
        app, "GET", f"/__routeflow__/traces/{trace_summary['trace_id']}"
    ).json()
    for field in ("trace_id", "started_at", "duration_ms", "status", "spans"):
        assert field in trace
    assert trace["status"] == "error"

    span_names = {span["name"] for span in trace["spans"]}
    assert span_names == {"validate_payment", "charge_card", "stripe_api_call"}

    stripe_span = next(s for s in trace["spans"] if s["name"] == "stripe_api_call")
    for field in (
        "span_id",
        "parent_id",
        "start_time",
        "duration_ms",
        "status",
        "args",
        "logs",
        "error",
    ):
        assert field in stripe_span
    assert stripe_span["status"] == "error"
    assert stripe_span["error"]["type"] == "TimeoutError"
    assert stripe_span["args"] == {"amount": "100"}

    # Error propagation the detail panel and node graph both rely on
    # rendering (see Phase 2/6): every ancestor on the failing path shows
    # errored too, not just the span that actually raised.
    charge_span = next(s for s in trace["spans"] if s["name"] == "charge_card")
    assert charge_span["status"] == "error"
    assert stripe_span["parent_id"] == charge_span["span_id"]
