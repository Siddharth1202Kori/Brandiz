"""Keyword reports through the DAL. Shared by API routers and worker jobs.

Cache keys include the provider name, so switching fake <-> DataForSEO never serves one
provider's numbers as the other's. Fresh provider results are also written to ClickHouse
`keyword_metrics` / `serp_snapshots` (best effort) for lists and the nightly refresh.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from seomaster_core.markets import Market
from seomaster_core.seo import KeywordMetrics, SerpSnapshot
from seomaster_providers.dal import DalRequest, DalResult, DataAccessLayer, FetchResult
from seomaster_providers.interfaces import IdeasMode, KeywordProvider

log = logging.getLogger(__name__)

OVERVIEW_TTL = timedelta(days=30)
IDEAS_TTL = timedelta(days=30)
SERP_TTL = timedelta(hours=24)
IDEAS_FETCH_LIMIT = 500  # rows pulled per ideas report; filters/sort/paging run on this set


class KeywordStore(Protocol):
    async def save_metrics(self, rows: list[KeywordMetrics]) -> None: ...
    async def save_serp(self, snap: SerpSnapshot) -> None: ...
    async def latest(self, market: Market, keywords: list[str]) -> dict[str, KeywordMetrics]: ...


@dataclass(frozen=True)
class Report[T]:
    data: T
    result: DalResult  # tier / source / fetched_at for the response meta


def overview_key(provider: str, market: Market, kw: str) -> str:
    return f"kw:{provider}:{market}:{kw}"


def ideas_key(provider: str, market: Market, mode: IdeasMode, seed: str) -> str:
    return f"ideas:{provider}:{market}:{mode}:{seed}"


def serp_key(provider: str, market: Market, kw: str) -> str:
    return f"serp:{provider}:{market}:{kw}"


@dataclass
class KeywordService:
    provider: KeywordProvider
    dal: DataAccessLayer
    store: KeywordStore

    async def overview(
        self, kw: str, market: Market, org_id: uuid.UUID | None, *, force: bool = False
    ) -> Report[KeywordMetrics]:
        async def fetch() -> FetchResult:
            priced = await self.provider.overview(kw, market)
            await self._save([priced.value])
            return FetchResult(priced.value.model_dump(mode="json"), priced.cost_usd)

        req = DalRequest(
            key=overview_key(self.provider.name, market, kw),
            ttl=OVERVIEW_TTL,
            provider=self.provider.name,
            endpoint="keyword.overview",
            org_id=org_id,
        )
        res = await self.dal.get(req, fetch, force=force)
        return Report(KeywordMetrics.model_validate(res.payload), res)

    async def ideas(
        self, seed: str, market: Market, mode: IdeasMode, org_id: uuid.UUID | None
    ) -> Report[list[KeywordMetrics]]:
        async def fetch() -> FetchResult:
            priced = await self.provider.ideas(seed, market, mode, IDEAS_FETCH_LIMIT)
            await self._save(priced.value)
            return FetchResult([m.model_dump(mode="json") for m in priced.value], priced.cost_usd)

        req = DalRequest(
            key=ideas_key(self.provider.name, market, mode, seed),
            ttl=IDEAS_TTL,
            provider=self.provider.name,
            endpoint=f"keyword.{mode}",
            org_id=org_id,
        )
        res = await self.dal.get(req, fetch)
        return Report([KeywordMetrics.model_validate(r) for r in res.payload], res)

    async def serp(self, kw: str, market: Market, org_id: uuid.UUID | None) -> Report[SerpSnapshot]:
        async def fetch() -> FetchResult:
            priced = await self.provider.serp(kw, market)
            try:
                await self.store.save_serp(priced.value)
            except Exception:
                log.exception("serp snapshot write failed")
            return FetchResult(priced.value.model_dump(mode="json"), priced.cost_usd)

        req = DalRequest(
            key=serp_key(self.provider.name, market, kw),
            ttl=SERP_TTL,
            provider=self.provider.name,
            endpoint="keyword.serp",
            org_id=org_id,
        )
        res = await self.dal.get(req, fetch)
        return Report(SerpSnapshot.model_validate(res.payload), res)

    async def _save(self, rows: list[KeywordMetrics]) -> None:
        if not rows:
            return
        try:
            await self.store.save_metrics(rows)
        except Exception:
            log.exception("keyword_metrics write failed")
