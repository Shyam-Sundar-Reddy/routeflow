from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import FastAPI

from routeflow import RouteFlow
from routeflow.tracing import track

# Regression coverage for a real bug report: with RouteFlow disabled
# (either path), a @track-ed endpoint raised RuntimeError from
# open_span() (no active trace to attach to) and FastAPI turned that
# into an unhandled 500 - exactly the scenario "leave @track in your
# code, flip the env var off in production" is supposed to make safe.
# No test exercised the enabled=False / ROUTEFLOW_ENABLED=0 path at all
# before this, for either the middleware or a @track-ed call - that gap
# is why this shipped unnoticed.


def _build_tracked_app() -> FastAPI:
    app = FastAPI()

    @track
    def build_greeting(name: str) -> str:
        return f"hello {name}"

    @app.get("/greet")
    def greet(name: str) -> dict[str, str]:
        return {"msg": build_greeting(name)}

    return app


def test_track_ed_endpoint_works_with_enabled_false(
    do_request: Callable[..., object],
) -> None:
    app = _build_tracked_app()
    RouteFlow(app, enabled=False)

    response = do_request(app, "GET", "/greet?name=world")

    assert response.status_code == 200
    assert response.json() == {"msg": "hello world"}
    # True no-op, not just "didn't crash" - no route mounted at all.
    assert do_request(app, "GET", "/__routeflow__/traces").status_code == 404


def test_track_ed_endpoint_works_with_env_var_disabled(
    do_request: Callable[..., object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ROUTEFLOW_ENABLED", "0")
    app = _build_tracked_app()
    RouteFlow(app)

    response = do_request(app, "GET", "/greet?name=world")

    assert response.status_code == 200
    assert response.json() == {"msg": "hello world"}
    assert do_request(app, "GET", "/__routeflow__/traces").status_code == 404


@pytest.mark.parametrize("falsy_value", ["0", "false", "False", "no", "off"])
def test_env_var_accepts_all_documented_falsy_spellings(
    do_request: Callable[..., object],
    monkeypatch: pytest.MonkeyPatch,
    falsy_value: str,
) -> None:
    monkeypatch.setenv("ROUTEFLOW_ENABLED", falsy_value)
    app = _build_tracked_app()
    RouteFlow(app)

    response = do_request(app, "GET", "/greet?name=world")

    assert response.status_code == 200
