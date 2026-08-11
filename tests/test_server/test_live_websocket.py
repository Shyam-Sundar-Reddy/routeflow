from __future__ import annotations

from fastapi import FastAPI
from starlette.testclient import TestClient


def test_websocket_receives_a_trace_when_a_request_completes(app: FastAPI) -> None:
    with TestClient(app) as client, client.websocket_connect(
        "/__routeflow__/live"
    ) as ws:
        response = client.get("/orders/7")
        assert response.status_code == 200

        message = ws.receive_json()

    assert message["path"] == "/orders/7"
    assert message["method"] == "GET"
    assert message["status"] == "ok"


def test_websocket_receives_multiple_traces_in_order(app: FastAPI) -> None:
    with TestClient(app) as client, client.websocket_connect(
        "/__routeflow__/live"
    ) as ws:
        client.get("/orders/1")
        client.get("/orders/2")

        first = ws.receive_json()
        second = ws.receive_json()

    assert first["path"] == "/orders/1"
    assert second["path"] == "/orders/2"
