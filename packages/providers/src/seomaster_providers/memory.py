"""In-memory DAL backends for unit tests and offline UI development."""

from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

from seomaster_core.markets import Market
from seomaster_core.seo import KeywordMetrics, SerpSnapshot
from seomaster_providers.dal import LedgerEntry, StoredPayload, utcnow


class MemoryHotCache:
    def __init__(self, now: Callable[[], datetime] = utcnow) -> None:
        self.now = now
        self.data: dict[str, tuple[str, datetime]] = {}
        self.spend: dict[str, Decimal] = {}
        self.fail = False  # flip to simulate an outage

    def _check(self) -> None:
        if self.fail:
            raise ConnectionError("hot cache down")

    async def get(self, key: str) -> str | None:
        self._check()
        hit = self.data.get(key)
        if hit is None or hit[1] <= self.now():
            return None
        return hit[0]

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        self._check()
        self.data[key] = (value, self.now() + timedelta(seconds=ttl_s))

    async def acquire(self, key: str, token: str, ttl_ms: int) -> bool:
        self._check()
        if await self.get(key) is not None:
            return False
        self.data[key] = (token, self.now() + timedelta(milliseconds=ttl_ms))
        return True

    async def release(self, key: str, token: str) -> None:
        self._check()
        if (hit := self.data.get(key)) and hit[0] == token:
            del self.data[key]

    async def add_spend(self, scope: str, usd: Decimal) -> None:
        self._check()
        self.spend[scope] = self.spend.get(scope, Decimal(0)) + usd

    async def get_spend(self, scope: str) -> Decimal:
        self._check()
        return self.spend.get(scope, Decimal(0))


class MemoryWarmStore:
    def __init__(self, now: Callable[[], datetime] = utcnow) -> None:
        self.now = now
        self.items: dict[str, StoredPayload] = {}

    async def get(self, key: str, *, allow_expired: bool = False) -> StoredPayload | None:
        item = self.items.get(key)
        if item and not allow_expired and item.expires_at <= self.now():
            return None
        return item

    async def put(self, item: StoredPayload) -> None:
        self.items[item.key] = item


class MemoryLedger:
    def __init__(self) -> None:
        self.entries: list[LedgerEntry] = []

    async def record(self, entry: LedgerEntry) -> None:
        self.entries.append(entry)


class MemoryKeywordStore:
    def __init__(self) -> None:
        self.metrics: dict[tuple[str, str], KeywordMetrics] = {}
        self.serps: list[SerpSnapshot] = []

    async def save_metrics(self, rows: list[KeywordMetrics]) -> None:
        for m in rows:
            key = (str(m.market), m.keyword)
            old = self.metrics.get(key)
            if old is None or old.fetched_at <= m.fetched_at:
                self.metrics[key] = m

    async def save_serp(self, snap: SerpSnapshot) -> None:
        self.serps.append(snap)

    async def latest(self, market: Market, keywords: list[str]) -> dict[str, KeywordMetrics]:
        return {
            k: self.metrics[(str(market), k)] for k in keywords if (str(market), k) in self.metrics
        }
