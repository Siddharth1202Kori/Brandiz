"""Per-request timing collector for the `server-timing` response header.

Any layer (DB, cache, provider) calls `record("db", ms)`; the API middleware renders
`server-timing: db;dur=12.3, cache;dur=0.8, total;dur=40.1`.
"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_timings: ContextVar[dict[str, float] | None] = ContextVar("timings", default=None)


def start() -> None:
    _timings.set({})


def record(name: str, ms: float) -> None:
    current = _timings.get()
    if current is not None:
        current[name] = current.get(name, 0.0) + ms


@contextmanager
def measure(name: str) -> Iterator[None]:
    t0 = time.perf_counter()
    try:
        yield
    finally:
        record(name, (time.perf_counter() - t0) * 1000)


def header_value(total_ms: float) -> str:
    parts = [f"{k};dur={v:.1f}" for k, v in (_timings.get() or {}).items()]
    parts.append(f"total;dur={total_ms:.1f}")
    return ", ".join(parts)
