"""DAL behaviour with in-memory backends: tiers, single-flight, budget guard, degradation."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from seomaster_providers.dal import (
    BudgetConfig,
    BudgetExceededError,
    DalRequest,
    DataAccessLayer,
    FetchResult,
)
from seomaster_providers.memory import MemoryHotCache, MemoryLedger, MemoryWarmStore


class Clock:
    def __init__(self) -> None:
        self.t = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.t


class Fetcher:
    def __init__(self, cost: str = "0.01", delay: float = 0.0) -> None:
        self.calls = 0
        self.cost = Decimal(cost)
        self.delay = delay

    async def __call__(self) -> FetchResult:
        self.calls += 1
        await asyncio.sleep(self.delay)
        return FetchResult(payload={"volume": 1000, "n": self.calls}, cost_usd=self.cost)


ORG = uuid.uuid4()


def make(
    budget_global: str = "5", budget_org: str = "1"
) -> tuple[DataAccessLayer, MemoryHotCache, MemoryLedger, Clock]:
    clock = Clock()
    hot, warm, ledger = MemoryHotCache(clock), MemoryWarmStore(clock), MemoryLedger()
    dal = DataAccessLayer(
        hot=hot,
        warm=warm,
        ledger=ledger,
        budget=BudgetConfig(Decimal(budget_global), Decimal(budget_org)),
        now=clock,
        poll_s=0.005,
        lock_wait_s=1.0,
    )
    return dal, hot, ledger, clock


def req(key: str = "kw:in:seo tools", ttl: timedelta = timedelta(days=30)) -> DalRequest:
    return DalRequest(key=key, ttl=ttl, provider="fake", endpoint="kw.overview", org_id=ORG)


async def test_miss_then_hot_hit() -> None:
    dal, _, ledger, _ = make()
    fetch = Fetcher()
    first = await dal.get(req(), fetch)
    second = await dal.get(req(), fetch)
    assert fetch.calls == 1
    assert (first.tier, second.tier) == ("provider", "hot")
    assert second.cached and not first.cached
    assert [e.cache_tier for e in ledger.entries] == ["provider", "hot"]
    assert ledger.entries[0].cost_usd == Decimal("0.01")
    assert ledger.entries[1].cost_usd == 0


async def test_warm_hit_rewarms_hot() -> None:
    dal, hot, _, _ = make()
    fetch = Fetcher()
    await dal.get(req(), fetch)
    hot.data.clear()  # e.g. Upstash eviction
    assert (await dal.get(req(), fetch)).tier == "warm"
    assert (await dal.get(req(), fetch)).tier == "hot"
    assert fetch.calls == 1


async def test_expired_entry_refetches() -> None:
    dal, _, _, clock = make()
    fetch = Fetcher()
    await dal.get(req(), fetch)
    clock.t += timedelta(days=31)
    assert (await dal.get(req(), fetch)).tier == "provider"
    assert fetch.calls == 2


async def test_single_flight_concurrent_misses() -> None:
    dal, _, ledger, _ = make()
    fetch = Fetcher(delay=0.05)
    results = await asyncio.gather(*(dal.get(req(), fetch) for _ in range(10)))
    assert fetch.calls == 1
    assert sum(r.tier == "provider" for r in results) == 1
    assert len(ledger.entries) == 10


async def test_budget_exceeded_serves_stale_copy() -> None:
    dal, _, _, clock = make(budget_org="0.01")
    fetch = Fetcher(cost="0.01")
    short = req(ttl=timedelta(hours=1))
    await dal.get(short, fetch)  # spends the org's whole daily budget
    clock.t += timedelta(hours=2)  # same day; cached copy expired
    result = await dal.get(short, fetch)
    assert result.tier == "stale" and result.stale
    assert fetch.calls == 1


async def test_budget_exceeded_without_stale_raises() -> None:
    dal, _, _, _ = make(budget_global="0.01")
    await dal.get(req("a"), Fetcher(cost="0.01"))
    with pytest.raises(BudgetExceededError) as exc:
        await dal.get(req("b"), Fetcher())
    assert exc.value.scope == "global"


async def test_budget_resets_next_day() -> None:
    dal, _, _, clock = make(budget_global="0.01")
    await dal.get(req("a"), Fetcher(cost="0.01"))
    clock.t += timedelta(days=1)
    assert (await dal.get(req("b"), Fetcher())).tier == "provider"


async def test_hot_cache_outage_degrades_to_warm() -> None:
    dal, hot, _, _ = make()
    fetch = Fetcher()
    await dal.get(req(), fetch)
    hot.fail = True
    result = await dal.get(req(), fetch)
    assert result.tier == "warm" and fetch.calls == 1
