"""A minimal FastAPI app instrumented with RouteFlow, for trying it out.

Run it:

    uv run --with fastapi --with uvicorn python examples/demo_app.py

Then hit a few requests (one of them fails on purpose, to show what an
error looks like in the flow view):

    curl -X POST "http://127.0.0.1:8000/orders?amount=120"
    curl -X POST "http://127.0.0.1:8000/orders?amount=999"   # amount > 500 -> fails

...and open the flow view:

    http://127.0.0.1:8000/flow/

Pick "POST /orders" in the sidebar, then a trace, to see the actual call
tree: get_user -> validate_payment -> charge_card -> stripe_api_call,
timed and (for the amount=999 request) showing exactly where it failed.
"""

from __future__ import annotations

import time

from fastapi import FastAPI

from routeflow import RouteFlow
from routeflow.tracing import track

app = FastAPI(title="RouteFlow demo shop")


@track
def get_user(user_id: int) -> dict:
    time.sleep(0.005)
    return {"id": user_id, "name": "sam"}


@track
def validate_payment(amount: int) -> bool:
    time.sleep(0.03)
    return amount > 0


@track
def stripe_api_call(amount: int) -> None:
    time.sleep(0.08)
    if amount > 500:
        raise TimeoutError("stripe timed out")


@track
def charge_card(amount: int) -> None:
    stripe_api_call(amount)


@track
def send_confirmation_email(order_id: int) -> None:
    time.sleep(0.01)


@app.post("/orders")
def create_order(amount: int, user_id: int = 1) -> dict:
    get_user(user_id)
    validate_payment(amount)
    charge_card(amount)
    send_confirmation_email(order_id=42)
    return {"amount": amount, "status": "ok"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


RouteFlow(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
