# routeflow

Real-time execution flow visualization for FastAPI applications.

**Status: early / pre-alpha.** This is the initial project scaffold; the
tracer, decorator, and node-graph UI described in [goal.md](./goal.md)
haven't been built yet.

## Why

FastAPI documents the *contract* of an API — routes, params, response
shapes — but says nothing about what actually happens when a request runs.
As soon as an app grows past a few endpoints, execution logic spreads across
services, middlewares, dependencies, and background tasks, and debugging
means mentally reconstructing a flow that should be visible in the first
place. `routeflow` aims to make that flow visible: mark functions or
services with a decorator, and see the real-time execution path rendered as
an interactive node graph — order, timing, logs, and errors, exactly where
they occur.

## Planned design

- **Capture**: a contextvars-based tracer with a `@routeflow.track` decorator
  that pushes/pops spans onto a per-request context, so it stays correct
  under async concurrency.
- **Storage**: in-memory ring buffer, dev-only — no persistence.
- **UI**: a local web UI streaming trace events over a WebSocket, rendered
  as an interactive node graph.

## Install

```bash
uv add routeflow
pip install routeflow
```

## Usage

```bash
routeflow about
routeflow --version
```

## Development

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
uv sync --extra dev    # install package + dev deps into .venv
uv run pytest -q       # run tests
uv run routeflow about # run the CLI
```
