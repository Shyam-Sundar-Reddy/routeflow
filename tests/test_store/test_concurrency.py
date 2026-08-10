from __future__ import annotations

import threading
from collections.abc import Callable

from routeflow.store import TraceStore
from routeflow.tracing import Trace

NUM_THREADS = 20
TRACES_PER_THREAD = 50
TOTAL = NUM_THREADS * TRACES_PER_THREAD


def test_concurrent_writes_dont_corrupt_the_store(
    make_trace: Callable[..., Trace],
) -> None:
    """The scenario the lock in TraceStore exists for: sync route
    handlers running in FastAPI's threadpool, all writing at once — not
    the single-event-loop case, where a lock wouldn't be needed. A
    buffer large enough that nothing evicts (`maxlen=TOTAL`) isolates
    "did every write land intact" from eviction behavior, which is
    already covered separately.
    """
    store = TraceStore(maxlen=TOTAL)

    def worker(thread_id: int) -> None:
        for i in range(TRACES_PER_THREAD):
            store.add(make_trace(path=f"/t{thread_id}-{i}"))

    threads = [
        threading.Thread(target=worker, args=(thread_id,))
        for thread_id in range(NUM_THREADS)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    all_traces = store.list_traces()

    assert len(store) == TOTAL
    assert len(all_traces) == TOTAL
    # No lost or duplicated writes — every trace_id present exactly once.
    assert len({trace.trace_id for trace in all_traces}) == TOTAL
