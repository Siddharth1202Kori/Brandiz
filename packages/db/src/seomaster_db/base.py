"""Async SQLAlchemy engine/session factory. DB time is reported to `server-timing`."""

import time
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from seomaster_core import timing


class Base(DeclarativeBase):
    pass


def make_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    engine = create_async_engine(url, echo=echo, pool_pre_ping=True, pool_size=5, max_overflow=5)
    _attach_timing(engine)
    return engine


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _attach_timing(engine: AsyncEngine) -> None:
    sync_engine = engine.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before(conn: Connection, *_: Any) -> None:
        conn.info.setdefault("_t0", []).append(time.perf_counter())

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after(conn: Connection, *_: Any) -> None:
        t0 = conn.info["_t0"].pop()
        timing.record("db", (time.perf_counter() - t0) * 1000)
