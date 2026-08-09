from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from routeflow.tracing.span import ErrorInfo, Span


def _new_trace_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Trace:
    """Everything captured for a single request.

    Holds the request's identifying info plus every `Span` recorded during
    it, keyed by span id. Parent/child structure lives on the spans
    themselves (`Span.parent_id`); `Trace` is just the flat collection scoped
    to one request.
    """

    method: str
    path: str
    trace_id: str = field(default_factory=_new_trace_id)
    route_pattern: str | None = None
    # perf_counter, matching Span — see the comment in span.py. Traces and
    # their spans must share one clock so offsets between them stay
    # meaningful (e.g. "this span started 40ms into the request").
    started_at: float = field(default_factory=time.perf_counter)
    ended_at: float | None = None
    status: str = "running"
    spans: dict[str, Span] = field(default_factory=dict)
    # Set when an exception escapes all the way to the middleware boundary
    # — not necessarily the same as any individual span erroring. An
    # untracked bug (in code never wrapped by @track) still needs to show
    # up somewhere; this is that somewhere.
    error: ErrorInfo | None = None

    @property
    def duration(self) -> float | None:
        """Wall-clock time the whole request took, in seconds."""
        if self.ended_at is None:
            return None
        return self.ended_at - self.started_at

    def record_error(self, exc: BaseException) -> None:
        """Attach an exception that escaped to the middleware boundary.

        Mirrors `Span.record_error` — does not raise or suppress anything;
        the middleware is still responsible for re-raising `exc` itself.
        """
        self.error = ErrorInfo.from_exception(exc)

    def finish(self) -> None:
        """Close the trace: record its end time and derive an overall
        status — "error" if the trace itself was marked errored
        (`record_error`) or any span errored, "ok" otherwise. Called once,
        by the middleware, when the response is ready (or the request
        failed).
        """
        self.ended_at = time.perf_counter()
        self.status = (
            "error" if self.error is not None or self._any_span_errored() else "ok"
        )

    def _any_span_errored(self) -> bool:
        return any(span.status == "error" for span in self.spans.values())

    def root_spans(self) -> list[Span]:
        """Top-level spans (no parent) — usually just the handler span,
        in call order.
        """
        roots = [span for span in self.spans.values() if span.parent_id is None]
        return sorted(roots, key=lambda span: span.start_time)

    def children_of(self, span_id: str) -> list[Span]:
        """Direct children of the given span, in call order.

        Used by the node-graph renderer to walk the tree one level at a
        time without every caller re-deriving parent/child links itself.
        """
        children = [
            span for span in self.spans.values() if span.parent_id == span_id
        ]
        return sorted(children, key=lambda span: span.start_time)
