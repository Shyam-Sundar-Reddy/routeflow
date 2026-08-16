# Architecture

How a request becomes a node graph, end to end. Written from the actual
source, not the original design — where the two disagreed, the code won.

## Module layout

```
src/routeflow/
├── tracing/
│   ├── span.py        Span, LogEntry, ErrorInfo
│   ├── trace.py         Trace
│   ├── context.py        ContextVar accessors (get/set/reset current trace/span)
│   ├── lifecycle.py       open_span, close_span, span_scope
│   └── decorator.py       @track — the public instrumentation API
├── middleware.py    RouteFlowMiddleware — the request boundary
├── store.py          TraceStore — in-memory ring buffer + aggregate stats
├── live.py             LiveBroadcaster — pushes finished traces over WebSocket
├── server.py           the mounted REST/WebSocket sub-app
├── integration.py       RouteFlow(app) — wires everything above together
└── frontend/             the flow-view UI (vanilla HTML/CSS/JS, no build step)
```

## The data model

**`Span`** — one traced call. `name`, `trace_id`, `parent_id` (`None` for a
root span), a generated `span_id`, `start_time`/`end_time`, `status`
(`"running"` → `"ok"` or `"error"`), `logs`, `args` (captured call
arguments, already stringified), and an optional `error`. `to_dict()`
gives a plain JSON-serializable snapshot — never the live object.

**`Trace`** — everything captured for one request. `method`, `path`,
`route_pattern`, a generated `trace_id`, `started_at`/`ended_at`, `status`,
an optional `error` (see "the middleware" below), and
`spans: dict[span_id, Span]` — a **flat** collection. There is no tree
object; the tree is derived on demand from `Span.parent_id` via
`Trace.root_spans()` and `Trace.children_of(span_id)`. `to_dict()` mirrors
`Span`'s — the whole trace as plain data, spans included as a flat list.

Both timestamps use `time.perf_counter()`, not `time.monotonic()`. On this
project's Windows dev machine, `monotonic()` is backed by `GetTickCount64()`
at ~15.6ms resolution — coarse enough that a fast function call could read
back as `0ms` duration. `perf_counter()` is the stdlib clock meant for
interval timing and is still monotonic, so it's a strict upgrade. `Span` and
`Trace` share this clock so offsets between them (e.g. "this span started
40ms into the request") stay meaningful.

## Context propagation

`context.py` holds two `ContextVar`s: the current trace and the current
span. They are **never** shared globals — each asyncio task (and thread)
gets its own view, which is what lets concurrent requests trace correctly
without stepping on each other. Two properties this depends on, verified in
`test_context_isolation.py`:

- Interleaved coroutines on one event loop each only ever see their own
  trace — setting a `ContextVar` in one doesn't leak into another that
  happens to be "in flight" at the same moment.
- `asyncio.create_task()` copies the current context **at creation time**.
  A child task doesn't see changes its parent makes afterward, and the
  parent doesn't see what the child sets. This is the propagation gap that
  `BackgroundTasks` / fire-and-forget tasks fall into if the context isn't
  copied across explicitly — not handled anywhere yet (see "not here yet").

## Lifecycle (`lifecycle.py`)

`open_span(name)` reads the current trace and current span, creates a
`Span` parented to whichever span is currently in scope (or root, if none),
and registers it on the trace. Called directly (not through `span_scope`),
it still raises if there's no active trace — a span with nowhere to
attach and no caller prepared to handle `None` is a bug in that caller.

`close_span(span)` records `end_time` and, if the span is still `"running"`
(i.e. nothing already called `record_error`), derives `"ok"`.

`span_scope(name)` is the context manager `@track` actually uses, and it
does **not** share `open_span`'s raise-on-no-trace behavior — with no
active trace at all (RouteFlow disabled via `ROUTEFLOW_ENABLED=0` /
`enabled=False`, or its middleware never installed), it's a true no-op:
yields `None` and runs the wrapped block exactly as if `@track` weren't
there. Bug, fixed: this used to call `open_span` unconditionally, so a
`@track`-ed function raised `RuntimeError` the moment tracing was
disabled — turning every traced endpoint into an unhandled 500 in
exactly the scenario `ROUTEFLOW_ENABLED=0` exists to make safe.
`get_current_span()` mirrors this — it returns a shared, harmless
placeholder span (not `None`) when there's no active trace at all, so
code like `get_current_span().log(...)` inside a `@track`-ed function
doesn't crash either; it still returns real `None` for the *other*
"no current span" case — a trace is active but nothing's been opened
yet — since `open_span` relies on that real `None` to mark a root span
correctly.

When a trace *is* active, `span_scope` opens a span, makes it current for
the block, and on exit — success or failure — restores the previous
current span and closes this one. If the block raises, the exception is
recorded on the span via `record_error` **and always re-raised
unchanged**. RouteFlow must never alter what traced code does, only
observe it — in both the traced and the disabled case alike.

One consequence worth knowing, not a bug: because the same exception
propagates through every enclosing `span_scope`, a failure marks **every
ancestor span** as `"error"`, each with its own captured `ErrorInfo` — not
just the span that originally raised. A sibling span that already finished
successfully before the failure is unaffected. This is what produces the
"raised in `stripe_api_call` → propagated to `charge_card` → propagated to
`handle_order`" chain the flow view shows.

`Trace.finish()` closes the trace and derives its overall status —
`"error"` if the trace itself was marked errored (see the middleware) or
any of its spans ended up `"error"`, `"ok"` otherwise.

## The decorator (`decorator.py`)

`@track` is a thin wrapper around `span_scope`, made safe to put on
arbitrary user functions:

- **Sync/async dispatch decided once, at decoration time**
  (`inspect.iscoroutinefunction`), not per call — a separate wrapper for
  each, since calling an `async def` the sync way only creates a coroutine
  object without running it.
- **Both `@track` and `@track(name=..., redact=..., capture_args=...)`**
  work, via a `func is None` check on the outer call.
- **Argument capture** binds `(*args, **kwargs)` to parameter names through
  the function's own `inspect.signature`, so a span records `amount=100`
  rather than an unlabeled positional list. `redact(name, value)` can mask
  or replace a specific argument before it's stringified; `capture_args=False`
  skips capture for the whole function (a raw credential, a full request
  body).
- **Generators are not supported yet** — calling a generator function only
  creates the generator object, it doesn't run the body, so the span would
  close almost instantly with a meaningless duration. Decorating one issues
  a `RuntimeWarning` rather than failing outright.

**`track_module(module, *, exclude=(), redact=None, capture_args=True)`**
applies `@track` to every function *defined in* a module, in place —
bulk convenience for onboarding an existing codebase without hand-adding
`@track` to each function. Deliberately not a global `auto_trace=True`
switch: that would capture arguments for functions nobody ever reviewed
for "does this take a password," the same silent-leak risk
`RouteFlow(app)`'s docstring warns about for the whole app, just
per-function. `track_module` stays a scoped, reviewable call site — a
`git diff` shows exactly which module opted in — while still composing
with per-function overrides (`exclude=`, or a manual `@track(...)`
applied before calling it). Two things are skipped automatically, not
just `exclude`: anything not a plain function *defined in that module*
(`func.__module__ == module.__name__` — a class, or a name merely
imported into the module's namespace, is left alone), and anything
already `@track`-ed (checked via a `__routeflow_tracked__` marker `track`
sets on its wrapper, not by re-inspecting behavior) — so calling it
twice, or over a module where a few functions were already hand-decorated,
never double-wraps. Scoped to top-level functions only; methods
(`__init__`, bound/unbound, inherited) are a large enough separate
problem to deliberately leave out rather than guess at.

## The middleware (`middleware.py`)

`RouteFlowMiddleware` is the request boundary — pure ASGI
(`scope`/`receive`/`send`), not Starlette's `BaseHTTPMiddleware`, which
buffers responses in ways that break streaming and can interfere with
`BackgroundTasks`.

Per HTTP request: open a `Trace`, set it as the current trace, run the
wrapped app, and in a `finally` — so this runs whether the request
succeeded or raised — derive the route pattern, close the trace, reset the
`ContextVar`, store the trace, and notify `on_trace` if one was given.

A few things worth knowing about *why* it's built this way:

- **Route pattern recovery is indirect.** The installed Starlette version
  doesn't put the matched `Route` object on `scope` — it writes
  `scope["endpoint"]` (the handler) and `scope["router"]`. The pattern
  (`/orders/{id}`, not `/orders/123`) is recovered by searching the
  router's routes for the one whose `.endpoint` matches. This was verified
  against the actual installed Starlette source, not assumed from older
  docs referencing `scope["route"]`, which doesn't exist here.
- **Exceptions are caught at the boundary too, not just in spans.** An
  exception that reaches here escaped *everything* below, including
  FastAPI's own exception handlers — genuinely unhandled failure. It's
  recorded on the `Trace` itself (`trace.record_error`), since it may not
  have happened inside any `@track`-ed span at all, then always re-raised
  unchanged.
- **`exclude_prefix` stops RouteFlow from tracing itself.** Without it, a
  browser polling the flow view's own `GET /__routeflow__/traces` would
  generate a trace for that request too, piling up as a bogus endpoint —
  confirmed happening before this existed. `RouteFlow(app)` passes its own
  mount path here.
- **`store`/`on_trace` are optional, injected dependencies**, not imports.
  The middleware doesn't know a `LiveBroadcaster` or WebSocket exists —
  `on_trace` is just "an async callable that takes a `Trace`."
  `RouteFlow(app)` wires the real ones in; used directly, the middleware
  defaults to a private `TraceStore()` so it's still usable standalone.

## Storage (`store.py`)

`TraceStore` is an in-memory `deque(maxlen=...)` — the oldest trace is
evicted automatically once full, no eviction logic to get wrong. Guarded by
a `threading.Lock`: a single asyncio event loop wouldn't need it (a
`deque.append` can't be interrupted mid-operation between `await` points),
but FastAPI runs plain `def` route handlers in a threadpool, so a write can
genuinely happen on a different OS thread at the same instant as another.

Reads (`list_traces`, `get`, `endpoint_stats`) copy out from under the lock
before returning, so a caller can't race a concurrent write mutating the
same deque underneath it. `endpoint_stats()` groups whatever's currently in
the buffer by `(method, route_pattern)` and computes request count, error
rate, and p95 latency fresh each call — there's no separate running total,
so a stat's window is implicitly "however far back the buffer currently
reaches." p95 uses linear-interpolation percentile (matching `numpy`'s
default) rather than `statistics.quantiles`, which refuses a single-value
sample — something a lightly-used endpoint will very often be.

## The server (`server.py`, `live.py`)

A small, standalone Starlette app — deliberately separate from the host's
own router rather than routes merged in via `include_router`. Mounting it
(`app.mount(...)`, in `integration.py`) gives it an isolated OpenAPI schema
for free: the host's `/docs` never learns these routes exist, and there's
no risk of colliding with a path the host app defines itself. Verified
against a real FastAPI app, not just assumed from how `mount` is
documented.

Routes: `GET /traces` (optionally filtered by `route_pattern`),
`GET /traces/{id}`, `GET /endpoints` (aggregate stats), `WS /live`. The
flow-view frontend itself is *not* one of these routes — it's mounted
separately, at bare `/flow` directly on the host app (see
`integration.py`), served as static files (`StaticFiles(..., html=True)`)
shipped inside the package so there's no separate frontend build/install
step.

None of these routes require authentication — a deliberate trade-off for
a local, dev-only tool (see the README's "No authentication" section),
not an oversight, but worth stating here plainly rather than leaving it
to be inferred from reading the routes themselves: anyone who can reach
the port can read every captured trace, including any unredacted
arguments. It's the reason `redact=`/`mask()`/`capture_args=False`
(`decorator.py`) matter as much as they do — there's no auth gate behind
them.

`LiveBroadcaster` tracks connected `/live` WebSocket clients in a `set`
(more than one flow-view tab can be open) and pushes each finished trace to
all of them via `broadcast_trace`. A stale connection failing `send_json`
is caught and dropped immediately, isolated per-client, so one dead socket
can't stop the trace from reaching everyone else.

## Wiring it together (`integration.py`)

`RouteFlow(app)` is the entire public install surface: creates a
`TraceStore` and a `LiveBroadcaster`, installs the middleware with both
wired in, and mounts *two* things — the REST/WS API (`server.py`) at the
collision-safe `/__routeflow__` prefix (`MOUNT_PATH`), and the flow-view
UI separately, at bare `/flow` (`FLOW_UI_PATH`) directly on the host app,
matching FastAPI's own `/docs`/`/redoc` rather than being buried under a
prefix. That second one is a real, deliberate trade-off: unlike
`MOUNT_PATH`, `/flow` is a plausible name a host app might already be
using for its own route — the same trade-off FastAPI itself accepts with
`/docs` (and exposes `docs_url=` to override). The middleware excludes
*both* prefixes from tracing itself.

**On by default, with an explicit off switch.** This is a dev tool — "add
one line, it just works" is the point — but traces can include captured
arguments and full stack traces, so it must never stay on silently in
production. `ROUTEFLOW_ENABLED=0` (also `false`/`no`/`off`) in the
environment disables it completely: no middleware installed, no route
mounted, `app` handed back untouched. `enabled=` overrides the environment
either way, for a caller that wants to decide in code
(`enabled=settings.debug`).

## The frontend (`frontend/`)

Vanilla HTML/CSS/JS, no framework, no build step — it's served as-is
directly from the package, so it has to run in a browser exactly as
written. Since the UI (`/flow`) and the API (`/__routeflow__`) are two
separate mounts now, `app.js` can only derive the host app's own root
from `window.location.pathname` (strip `flow/` off whatever URL loaded
the page) — the API base then has to be that root plus the fixed,
known `__routeflow__/` prefix, since it's no longer nested inside the
page's own URL the way it was before the UI moved to a bare path.

Sidebar (`GET /endpoints`) → trace list for the selected endpoint
(`GET /traces?route_pattern=...`) → node graph for the selected trace,
built from that trace's flat span list the same way `Trace.children_of`
does. A `WebSocket` connection to `/live` appends new traces as they
finish, with reconnect-on-drop and a small connection-status indicator.
Theme is token-based CSS custom properties — `prefers-color-scheme` for the
OS default, a `[data-theme]` attribute for the manual toggle, persisted in
`localStorage`.

## What's deliberately not here yet

- **Context propagation across `asyncio.create_task()` / `BackgroundTasks`**
  isn't handled — a fire-and-forget task started inside a traced request
  won't automatically attribute its own `@track`ed calls back to that
  request's trace, for the reason described above under "context
  propagation."
- **No packaging/release yet** — not published to PyPI; install from
  source for now.
