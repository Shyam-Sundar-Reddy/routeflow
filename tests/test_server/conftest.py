from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI

from routeflow import RouteFlow


@pytest.fixture
def app() -> FastAPI:
    """A real FastAPI app, wired up with RouteFlow exactly the way a
    user would — the REST/WebSocket endpoints are tested against this,
    not against `build_server_app` in isolation, so a test failure here
    means the actual installed product is broken, not just one module.
    """
    fastapi_app = FastAPI()

    @fastapi_app.get("/orders/{id}")
    def get_order(id: int) -> dict[str, int]:
        return {"id": id}

    @fastapi_app.get("/crash")
    def crash() -> None:
        raise RuntimeError("unhandled boom")

    RouteFlow(fastapi_app)
    return fastapi_app


def _do_request(
    app: FastAPI, method: str, path: str, *, raise_app_exceptions: bool = False
) -> httpx.Response:
    async def call() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=app, raise_app_exceptions=raise_app_exceptions
        )
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.request(method, path)

    return asyncio.run(call())


@pytest.fixture
def do_request():
    """Exposed as a fixture (not a plain import) for the same reason as
    `tests/test_middleware/conftest.py`'s version — pytest wires it up
    via fixture discovery, so tests don't need `tests` to be an
    importable package.
    """
    return _do_request
