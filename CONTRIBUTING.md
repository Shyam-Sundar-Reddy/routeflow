# Contributing to routeflow

## Setup

This project uses [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev    # installs the package + dev deps (pytest, httpx, fastapi) into .venv
uv run pytest -q       # run the test suite
```

CI runs the same suite on Python 3.12 and 3.13. If you can, check both
locally before pushing:

```bash
uv run pytest -q                              # whatever .venv is currently pinned to
uv run --python 3.13 --extra dev pytest -q    # the other one
uv sync --extra dev                           # restore .venv afterward - the 3.13 run above rebuilds it
```

## Where things live

```
src/routeflow/
├── tracing/        Span/Trace data model, ContextVar plumbing, the @track decorator
├── middleware.py    ASGI middleware — opens/closes a trace per request
├── store.py         in-memory ring buffer + aggregate stats
├── server.py         the mounted REST/WebSocket sub-app
├── live.py           WebSocket broadcaster
├── integration.py    RouteFlow(app) — the public one-line install
└── frontend/          the flow-view UI (vanilla HTML/CSS/JS, no build step)

tests/
├── test_tracing/     unit tests for the span/trace model in isolation
├── test_middleware/  tests against a real ASGI app (httpx.ASGITransport)
└── test_server/      tests against a real FastAPI app (TestClient)
```

[ARCHITECTURE.md](./ARCHITECTURE.md) covers the tracing core's design in
more depth — the `ContextVar` propagation model in particular is worth
reading before touching `tracing/` or `middleware.py`.

## Conventions this codebase actually follows

- **Comments explain *why*, not *what*.** Code here tends to have a short
  comment wherever a decision isn't obvious from the line itself — a
  platform gotcha, a deliberate trade-off, a "this looks wrong but isn't."
  Match that density rather than either bare code or narrating every line.
- **Never alter behavior, only observe it.** The decorator and middleware
  both follow the same shape: `except`, record, `raise` unchanged. Any new
  instrumentation point should too — RouteFlow must never be able to change
  what a traced app does or returns.
- **Tests against the real thing, not mocks.** `test_middleware/` and
  `test_server/` build a real Starlette/FastAPI app and drive it with
  `httpx`/`TestClient` rather than mocking ASGI internals — that's what
  caught the `scope["route"]` assumption that turned out to be wrong for
  the installed Starlette version (see the comment in `middleware.py`).
  Verify an assumption against the real library before writing a test that
  encodes it.
- **Conventional commits, one concern each.** `feat(scope): ...`,
  `fix: ...`, `test(scope): ...`, `docs: ...` — small enough that each
  commit builds and passes tests on its own.

## Before opening a PR

- `uv run pytest -q` passes.
- New behavior has a test that would fail without the change.
- If you touched `tracing/` or `middleware.py`, skim
  [ARCHITECTURE.md](./ARCHITECTURE.md) for whether it needs updating too.
