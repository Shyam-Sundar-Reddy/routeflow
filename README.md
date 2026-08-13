# routeflow

Real-time execution flow visualization for FastAPI applications.

FastAPI documents the *contract* of an API — routes, params, response
shapes — but says nothing about what actually happens when a request runs.
As soon as an app grows past a few endpoints, execution logic spreads across
services, middleware, dependencies, and background tasks, and debugging
means mentally reconstructing a flow that should have been visible in the
first place.

`routeflow` makes that flow visible: mark a function with `@track`, and
every request that calls it gets traced — order, timing, logs, and errors —
and rendered live as an interactive node graph in a tab next to your
Swagger docs.

**Status:** functional for local development — the tracer, middleware,
in-memory store, and flow-view UI all work end to end. Not yet published to
PyPI; install from source for now (see below).

## Quickstart

```bash
pip install routeflow
```

```python
from fastapi import FastAPI
from routeflow import RouteFlow
from routeflow.tracing import track

app = FastAPI()
RouteFlow(app)


@track
def charge_card(amount: int) -> None:
    ...  # call out to whatever actually charges the card


@app.post("/orders")
def create_order(amount: int):
    charge_card(amount)
    return {"amount": amount, "status": "ok"}
```

Run it (`uvicorn myapp:app`), hit `POST /orders`, then open:

```
http://127.0.0.1:8000/__routeflow__/app/
```

That's the flow view — pick an endpoint in the sidebar, pick a trace, and
you'll see the request's actual call tree: which functions ran, in what
order, how long each took, and — if something raised — exactly where.

## What `@track` gives you

- **Nested spans, for free.** Call another `@track`-decorated function from
  inside one, and the call tree builds itself via `contextvars` — no
  manual parent/child wiring.
- **Sync and async.** Works on both `def` and `async def` the same way.
- **Arguments, captured and redactable.** Call args are recorded on the
  span by name; pass `redact=` to mask specific ones (a password, a token)
  or `capture_args=False` to skip a function entirely.
- **Errors, observed not altered.** An exception is recorded on the span
  and then always re-raised unchanged — RouteFlow never changes what your
  code does, only what you can see about it.

## The flow view

- Sidebar lists every endpoint that's been hit, with request count, p95
  latency, and error rate.
- Pick an endpoint to see its recent traces; pick a trace to see its node
  graph — timing and status on every node, an error highlighted exactly
  where it happened.
- Updates live over a WebSocket as new requests come in — no refresh
  needed.
- Sits in its own tab next to your existing Swagger `/docs`, light/dark
  themed.

## Turning it off

RouteFlow is on by default — it's a dev tool, and "add one line, it just
works" is the point. But traces can include captured arguments and full
stack traces, so it must never ship to production silently:

```bash
ROUTEFLOW_ENABLED=0
```

set in the environment disables it completely — no middleware installed, no
route mounted, your app handed back untouched. `RouteFlow(app, enabled=False)`
does the same from code, e.g. `enabled=settings.debug`.

## Try it

[`examples/demo_app.py`](./examples/demo_app.py) is a small shop app with a
nested call tree and one request that fails on purpose, so there's
something worth looking at the first time you open the flow view:

```bash
uv run --with fastapi --with uvicorn python examples/demo_app.py
```

## How it works

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the mechanism: the
`contextvars`-based span model, the ASGI middleware that opens/closes a
trace per request, the in-memory ring buffer, and the mounted REST/WebSocket
server the flow view reads from.

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
uv sync --extra dev    # install package + dev deps into .venv
uv run pytest -q       # run tests
uv run routeflow about # run the CLI
```
