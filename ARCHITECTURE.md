# Architecture — tracing core (Phase 1)

This documents `src/routeflow/tracing/`: the span/trace data model and the
`ContextVar` plumbing everything else in RouteFlow builds on. No FastAPI
integration lives here yet — that's the `@track` decorator (Phase 2) and the
ASGI middleware (Phase 3), both of which sit on top of this module without
changing it.

## Module layout

```
src/routeflow/tracing/
├── span.py        Span, LogEntry, ErrorInfo
├── trace.py        Trace
├── context.py       ContextVar accessors (get/set/reset current trace/span)
└── lifecycle.py      open_span, close_span, span_scope
```

## The data model

**`Span`** — one traced call. `name`, `trace_id`, `parent_id` (`None` for a
root span), a generated `span_id`, `start_time`/`end_time`, `status`
(`"running"` → `"ok"` or `"error"`), `logs`, and an optional `error`.

**`Trace`** — everything captured for one request. `method`, `path`,
`route_pattern`, a generated `trace_id`, `started_at`/`ended_at`, `status`,
and `spans: dict[span_id, Span]` — a **flat** collection. There is no tree
object; the tree is derived on demand from `Span.parent_id` via
`Trace.root_spans()` and `Trace.children_of(span_id)`.

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
  copied across explicitly — not yet handled here, since nothing in Phase 1
  creates background tasks.

## Lifecycle

`open_span(name)` reads the current trace and current span, creates a
`Span` parented to whichever span is currently in scope (or root, if none),
and registers it on the trace. It raises if called with no active trace —
a span with nowhere to attach is a caller bug, not something to silently
drop.

`close_span(span)` records `end_time` and, if the span is still `"running"`
(i.e. nothing already called `record_error`), derives `"ok"`.

`span_scope(name)` is the context manager that ties these together: opens
a span, makes it current for the block, and on exit — success or
failure — restores the previous current span and closes this one. If the
block raises, the exception is recorded on the span via `record_error`
**and always re-raised unchanged**. RouteFlow must never alter what traced
code does, only observe it.

One consequence worth knowing, not a bug: because the same exception
propagates through every enclosing `span_scope`, a failure marks **every
ancestor span** as `"error"`, each with its own captured `ErrorInfo` — not
just the span that originally raised. A sibling span that already finished
successfully before the failure is unaffected. This is what produces the
"raised in `stripe_api_call` → propagated to `charge_card` → propagated to
`handle_order`" chain the Flow tab is meant to show.

`Trace.finish()` closes the trace and derives its overall status —
`"error"` if any of its spans ended up `"error"`, `"ok"` otherwise. Nothing
in Phase 1 calls this automatically; it's meant to be called once, by the
middleware, when the response is ready.

## What's deliberately not here yet

- No decorator — `open_span`/`span_scope` are called directly in tests.
  `@track` (Phase 2) is a thin sync/async-aware wrapper around
  `span_scope` plus argument capture.
- No request boundary — nothing here sets the *first* trace on a request.
  The ASGI middleware (Phase 3) is what calls `set_current_trace` at
  request start and `Trace.finish()` at response time, and is what reads
  `scope["route"]` for `route_pattern`.
- No storage or serialization — traces live only as Python objects for
  now. The ring buffer and JSON serialization are Phase 4.
