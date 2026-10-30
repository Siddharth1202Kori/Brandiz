"""Health: DB, Redis, ClickHouse, worker heartbeat. Also used by the SPA as a wake-up ping."""

import asyncio
import time
from collections.abc import Awaitable
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import text

router = APIRouter(tags=["health"])

HEARTBEAT_KEY = "worker:heartbeat"
HEARTBEAT_STALE_S = 15 * 60


async def _check(coro: Awaitable[Any]) -> dict[str, Any]:
    t0 = time.perf_counter()
    try:
        await asyncio.wait_for(coro, timeout=2)
        return {"ok": True, "ms": round((time.perf_counter() - t0) * 1000, 1)}
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}


async def _db(request: Request) -> None:
    async with request.app.state.engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


async def _clickhouse(request: Request) -> None:
    client = await request.app.state.clickhouse.client()
    await client.query("SELECT 1")


async def _worker(request: Request) -> dict[str, Any]:
    try:
        raw = await request.app.state.redis.get(HEARTBEAT_KEY)
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}
    if raw is None:
        return {"ok": False, "error": "no_heartbeat"}
    age = time.time() - float(raw)
    return {"ok": age < HEARTBEAT_STALE_S, "age_s": round(age)}


@router.get("/healthz")
@router.get("/api/v1/healthz")
async def healthz(request: Request) -> dict[str, Any]:
    db, redis, ch = await asyncio.gather(
        _check(_db(request)),
        _check(request.app.state.redis.ping()),
        _check(_clickhouse(request)),
    )
    checks = {"postgres": db, "redis": redis, "clickhouse": ch, "worker": await _worker(request)}
    status = "ok" if all(c["ok"] for c in checks.values()) else "degraded"
    return {"status": status, "checks": checks}
