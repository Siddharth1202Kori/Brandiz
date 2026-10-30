"""Normalized SEO domain models returned by provider adapters.

Field names follow what Semrush exposes (doc 02 §5) so reports map 1:1. Phases 1-5 extend
these; Phase 0 only needs them for the provider interfaces and the fake provider.
"""

from datetime import date, datetime

from pydantic import BaseModel

from seomaster_core.markets import Market


class KeywordMetrics(BaseModel):
    keyword: str
    market: Market
    volume: int | None = None
    cpc: float | None = None
    competition: float | None = None
    kd: int | None = None
    intents: list[str] = []  # main intent first
    trend: list[int | None] = []  # monthly volume, oldest -> newest (12 months)
    trend_months: list[str] = []  # "YYYY-MM" labels aligned with `trend`
    serp_features: list[str] = []
    source: str
    fetched_at: datetime

    @property
    def has_data(self) -> bool:
        return self.volume is not None or self.kd is not None or self.cpc is not None


class SerpItem(BaseModel):
    position: int
    url: str
    domain: str
    title: str | None = None


class SerpSnapshot(BaseModel):
    keyword: str
    market: Market
    device: str = "desktop"
    items: list[SerpItem]
    features: list[str] = []
    taken_at: datetime


class DomainOverview(BaseModel):
    domain: str
    market: Market
    organic_keywords: int | None = None
    organic_traffic: int | None = None
    traffic_cost: float | None = None
    fetched_at: datetime


class RankedKeyword(BaseModel):
    keyword: str
    position: int
    url: str
    volume: int | None = None
    traffic: float | None = None


class Competitor(BaseModel):
    domain: str
    common_keywords: int
    overlap_pct: float | None = None


class BacklinkSummary(BaseModel):
    target: str
    rank: int | None = None
    backlinks: int | None = None
    ref_domains: int | None = None
    dofollow: int | None = None
    nofollow: int | None = None
    fetched_at: datetime


class Backlink(BaseModel):
    source_url: str
    target_url: str
    anchor: str | None = None
    dofollow: bool = True
    first_seen: date | None = None


class RefDomain(BaseModel):
    domain: str
    backlinks: int
    rank: int | None = None


class Anchor(BaseModel):
    text: str
    backlinks: int
    ref_domains: int | None = None


class RankCheck(BaseModel):
    keyword: str
    market: Market
    device: str = "desktop"
    location_code: int | None = None


class RankResult(BaseModel):
    check: RankCheck
    serp: SerpSnapshot


class GscSite(BaseModel):
    site_url: str
    permission_level: str


class GscQuery(BaseModel):
    start_date: date
    end_date: date
    dimensions: list[str] = ["date"]
    row_limit: int = 25000
    start_row: int = 0


class GscRow(BaseModel):
    keys: list[str]
    clicks: float
    impressions: float
    ctr: float
    position: float
