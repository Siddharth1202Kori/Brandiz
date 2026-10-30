"""KeywordService over the DAL with in-memory backends: caching, ledger, store writes."""

from decimal import Decimal

from seomaster_core.markets import Market
from seomaster_providers.dal import BudgetConfig, DataAccessLayer
from seomaster_providers.fake import FakeKeywordProvider
from seomaster_providers.keywords import KeywordService
from seomaster_providers.memory import (
    MemoryHotCache,
    MemoryKeywordStore,
    MemoryLedger,
    MemoryWarmStore,
)


def service() -> tuple[KeywordService, FakeKeywordProvider, MemoryLedger, MemoryKeywordStore]:
    provider = FakeKeywordProvider()
    ledger = MemoryLedger()
    store = MemoryKeywordStore()
    dal = DataAccessLayer(
        hot=MemoryHotCache(),
        warm=MemoryWarmStore(),
        ledger=ledger,
        budget=BudgetConfig(daily_global_usd=Decimal(5), daily_org_usd=Decimal(1)),
    )
    return KeywordService(provider, dal, store), provider, ledger, store


async def test_second_identical_overview_makes_no_provider_call() -> None:
    svc, provider, ledger, store = service()
    first = await svc.overview("seo tools", Market.IN, None)
    second = await svc.overview("seo tools", Market.IN, None)
    assert provider.calls == 1
    assert first.data == second.data
    assert [e.cache_tier for e in ledger.entries] == ["provider", "hot"]
    assert ledger.entries[0].cost_usd > 0 and ledger.entries[1].cost_usd == 0
    assert ledger.entries[0].cache_key == "kw:fake:in:seo tools"
    assert ("in", "seo tools") in store.metrics  # normalized row written once


async def test_markets_are_cached_separately() -> None:
    svc, provider, _, _ = service()
    await svc.overview("seo tools", Market.IN, None)
    await svc.overview("seo tools", Market.US, None)
    assert provider.calls == 2


async def test_force_refresh_bypasses_cache() -> None:
    svc, provider, ledger, _ = service()
    await svc.overview("seo tools", Market.US, None)
    await svc.overview("seo tools", Market.US, None, force=True)
    assert provider.calls == 2
    assert [e.cache_tier for e in ledger.entries] == ["provider", "provider"]


async def test_ideas_cached_per_mode_and_stored() -> None:
    svc, provider, ledger, store = service()
    a = await svc.ideas("seo", Market.US, "ideas", None)
    b = await svc.ideas("seo", Market.US, "ideas", None)
    await svc.ideas("seo", Market.US, "related", None)
    assert provider.calls == 3 - 1  # second "ideas" was a cache hit
    assert a.data == b.data and len(a.data) > 10
    assert {e.endpoint for e in ledger.entries} == {"keyword.ideas", "keyword.related"}
    assert len(store.metrics) >= len(a.data)


async def test_serp_snapshot_cached_and_recorded() -> None:
    svc, provider, _, store = service()
    snap = await svc.serp("seo tools", Market.US, None)
    await svc.serp("seo tools", Market.US, None)
    assert provider.calls == 1
    assert len(snap.data.items) == 10
    assert len(store.serps) == 1


async def test_store_failure_does_not_break_report() -> None:
    svc, _, _, store = service()

    async def boom(*_: object) -> None:
        raise ConnectionError("clickhouse down")

    store.save_metrics = boom  # type: ignore[method-assign]
    report = await svc.overview("seo tools", Market.US, None)
    assert report.data.volume is not None
