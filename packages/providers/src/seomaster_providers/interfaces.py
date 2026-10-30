"""Provider contracts (doc 03 §4.1). Adapters for DataForSEO / SERP API / GSC implement these."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from seomaster_core.markets import Market
from seomaster_core.models import Page, PageOpts
from seomaster_core.seo import (
    Anchor,
    Backlink,
    BacklinkSummary,
    Competitor,
    DomainOverview,
    GscQuery,
    GscRow,
    GscSite,
    KeywordMetrics,
    RankCheck,
    RankedKeyword,
    RankResult,
    RefDomain,
    SerpSnapshot,
)

IdeasMode = Literal["ideas", "related", "suggestions"]


@dataclass(frozen=True)
class Priced[T]:
    """A provider result plus what it cost; the DAL writes `cost_usd` to the ledger."""

    value: T
    cost_usd: Decimal = Decimal(0)


class KeywordProvider(Protocol):
    """Keywords must already be normalized (`seomaster_core.keywords.normalize_keyword`)."""

    name: str

    async def overview(self, kw: str, market: Market) -> Priced[KeywordMetrics]: ...
    async def ideas(
        self, seed: str, market: Market, mode: IdeasMode, limit: int
    ) -> Priced[list[KeywordMetrics]]: ...
    async def serp(self, kw: str, market: Market) -> Priced[SerpSnapshot]: ...
    async def difficulty(
        self, keywords: list[str], market: Market
    ) -> Priced[dict[str, int | None]]: ...
    async def intents(
        self, keywords: list[str], market: Market
    ) -> Priced[dict[str, list[str]]]: ...
    async def post_volume_task(self, keywords: list[str], market: Market) -> Priced[str]:
        """Queue a (cheaper) bulk volume job; returns the provider task id."""
        ...

    async def get_volume_task(self, task_id: str, market: Market) -> list[KeywordMetrics] | None:
        """Results of a queued volume job, or None while it is still running."""
        ...


class DomainProvider(Protocol):
    name: str

    async def overview(self, domain: str, market: Market) -> DomainOverview: ...
    async def ranked_keywords(
        self, domain: str, market: Market, opts: PageOpts
    ) -> Page[RankedKeyword]: ...
    async def competitors(self, domain: str, market: Market) -> list[Competitor]: ...


class BacklinkProvider(Protocol):
    name: str

    async def summary(self, target: str) -> BacklinkSummary: ...
    async def backlinks(self, target: str, opts: PageOpts) -> Page[Backlink]: ...
    async def ref_domains(self, target: str, opts: PageOpts) -> Page[RefDomain]: ...
    async def anchors(self, target: str, opts: PageOpts) -> Page[Anchor]: ...


class RankProvider(Protocol):
    name: str

    async def check_positions(self, batch: list[RankCheck]) -> list[RankResult]: ...


class FirstPartyProvider(Protocol):
    name: str

    async def sites(self, user_id: str) -> list[GscSite]: ...
    async def search_analytics(self, site: str, q: GscQuery) -> list[GscRow]: ...
