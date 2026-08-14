"""A deeper, production-shaped async example: API -> service -> repository/
gateway -> client layers, concurrent fan-out via asyncio.gather, log lines,
argument redaction, a deterministic failure path, and a flaky one - built to
actually stress the flow view rather than just prove it renders.

Run it:

    uv run --with fastapi --with "uvicorn[standard]" python examples/production_demo.py

`uvicorn[standard]`, not plain `uvicorn` - the flow view's live updates
silently can't work without a WebSocket implementation installed
(`websockets` or `wsproto`); plain `uvicorn` doesn't include one.

Try:

    # a normal checkout - 3 items, succeeds
    curl -X POST "http://127.0.0.1:8000/checkout?order_id=1&user_id=7"

    # >=8 items pushes the total over the gateway's failure threshold
    curl -X POST "http://127.0.0.1:8000/checkout?order_id=2&items=1,2,3,4,5,6,7,8"

    # fire a burst of concurrent checkouts, to see each get its own
    # correctly-isolated trace (the ContextVar propagation this whole
    # project is built around)
    for i in 10 11 12 13 14; do
        curl -s -X POST "http://127.0.0.1:8000/checkout?order_id=$i&user_id=$i" &
    done; wait

Then open http://127.0.0.1:8000/flow/ and pick "POST /checkout".

What to look for in the graph:
  - one root span (checkout_service_process_checkout) with a deep call
    tree under it - service -> repository/gateway -> client, several
    layers, not a flat list of siblings.
  - inventory + pricing run concurrently (asyncio.gather) but still both
    show up correctly nested under the same parent.
  - email + sms also run concurrently; sms fails about 30% of the time
    (return_exceptions=True) - notice the request still succeeds overall
    even when that one leaf is red.
  - payment_gateway_charge has no captured args at all (capture_args=False
    - a raw card number shouldn't be written to a trace); sms_client_send
    shows phone as "***" (redact=) instead.
"""

from __future__ import annotations

import asyncio
import random

from fastapi import FastAPI

from routeflow import RouteFlow
from routeflow.tracing import get_current_span, track

app = FastAPI(title="RouteFlow production-shape demo")


# ---- clients: lowest layer, pretend I/O -------------------------------------


@track
async def db_client_execute(query: str) -> dict:
    await asyncio.sleep(0.02)
    get_current_span().log(f"executed: {query}")
    return {"rows": 1}


@track
async def stripe_gateway_charge(amount_cents: int, card_number: str) -> dict:
    await asyncio.sleep(0.09)
    get_current_span().log("POST https://api.stripe.com/v1/charges")
    if amount_cents >= 20_000:
        raise TimeoutError("stripe gateway timed out")
    return {"charge_id": "ch_demo123"}


@track
async def email_client_send(to: str, subject: str) -> None:
    await asyncio.sleep(0.03)


@track(redact=lambda name, value: "***" if name == "phone" else value)
async def sms_client_send(phone: str, message: str) -> None:
    await asyncio.sleep(0.05)
    if random.random() < 0.3:
        raise ConnectionError("sms provider unreachable")


@track
async def cache_get(key: str) -> dict | None:
    await asyncio.sleep(0.002)
    return None  # always a miss here, to show the fallback path below


@track
async def cache_set(key: str, value: dict) -> None:
    await asyncio.sleep(0.002)


# ---- repositories / gateways: middle layer ----------------------------------


@track
async def order_repository_save(order_id: int, total_cents: int) -> None:
    await db_client_execute(
        f"INSERT INTO orders (id, total) VALUES ({order_id}, {total_cents})"
    )


@track
async def inventory_repository_reserve(item_ids: list[int]) -> None:
    await db_client_execute(
        f"UPDATE inventory SET reserved=true WHERE id IN {tuple(item_ids)}"
    )


@track
async def pricing_repository_lookup(item_ids: list[int]) -> int:
    await db_client_execute(f"SELECT price FROM items WHERE id IN {tuple(item_ids)}")
    return len(item_ids) * 2500  # cents


@track(capture_args=False)  # a raw card number shouldn't be written to a trace at all
async def payment_gateway_charge(amount_cents: int, card_number: str) -> dict:
    return await stripe_gateway_charge(amount_cents, card_number)


# ---- services: business logic layer -----------------------------------------


@track
async def inventory_service_reserve(item_ids: list[int]) -> None:
    await inventory_repository_reserve(item_ids)


@track
async def pricing_service_calculate_total(item_ids: list[int]) -> int:
    return await pricing_repository_lookup(item_ids)


@track
async def payment_service_charge(user_id: int, amount_cents: int, card_number: str) -> dict:
    return await payment_gateway_charge(amount_cents, card_number)


@track
async def notification_service_notify(phone: str, email: str) -> None:
    # Fan-out: two independent channels, sent concurrently. One failing
    # (sms, ~30% of the time) must not take the whole checkout down with
    # it - return_exceptions=True is what keeps that isolated.
    await asyncio.gather(
        email_client_send(email, "Your order is confirmed"),
        sms_client_send(phone, "Order confirmed!"),
        return_exceptions=True,
    )


@track
async def user_service_get_user(user_id: int) -> dict:
    cached = await cache_get(f"user:{user_id}")
    if cached is not None:
        return cached
    await db_client_execute(f"SELECT * FROM users WHERE id={user_id}")
    user = {"id": user_id, "email": f"user{user_id}@example.com", "phone": "+15551234567"}
    await cache_set(f"user:{user_id}", user)
    return user


# ---- orchestrator: one root span per request ---------------------------------


@track
async def checkout_service_process_checkout(
    order_id: int, user_id: int, item_ids: list[int], card_number: str
) -> dict:
    user = await user_service_get_user(user_id)

    # Fan-out: reserving inventory and pricing don't depend on each other.
    _, total_cents = await asyncio.gather(
        inventory_service_reserve(item_ids),
        pricing_service_calculate_total(item_ids),
    )

    charge = await payment_service_charge(user_id, total_cents, card_number)

    await order_repository_save(order_id, total_cents)
    await notification_service_notify(user["phone"], user["email"])

    return {"order_id": order_id, "total_cents": total_cents, "charge_id": charge["charge_id"]}


# ---- API layer ----------------------------------------------------------------


@app.post("/checkout")
async def checkout(
    order_id: int,
    user_id: int = 1,
    items: str = "1,2,3",
    card_number: str = "4242424242424242",
):
    item_ids = [int(x) for x in items.split(",")]
    return await checkout_service_process_checkout(order_id, user_id, item_ids, card_number)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


RouteFlow(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
