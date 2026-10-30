"""Production DAL backends: Redis (hot cache, locks, spend) and ClickHouse (warm store, ledger)."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from clickhouse_connect.driver.asyncclient import AsyncClient
from redis.asyncio import Redis

from seomaster_core.markets import Market
from seomaster_core.seo import KeywordMetrics, SerpSnapshot
from seomaster_providers.dal import LedgerEntry, StoredPayload

_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""
_SPEND_TTL_S = 2 * 24 * 3600
_GET_ANY = (
    "SELECT key, provider, endpoint, payload, fetched_at, expires_at FROM provider_payloads "
    "WHERE key = {key:String} ORDER BY fetched_at DESC LIMIT 1"
)
_GET_FRESH = (
    "SELECT key, provider, endpoint, payload, fetched_at, expires_at FROM provider_payloads "
    "WHERE key = {key:String} AND expires_at > now64(3) ORDER BY fetched_at DESC LIMIT 1"
)


class ClientSource(Protocol):
    """Anything that hands out a connected ClickHouse client (e.g. ClickHouseHandle)."""

    async def client(self) -> AsyncClient: ...


class RedisHotCache:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def get(self, key: str) -> str | None:
        value: str | None = await self.redis.get(key)
        return value

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        await self.redis.set(key, value, ex=ttl_s)

    async def acquire(self, key: str, token: str, ttl_ms: int) -> bool:
        return bool(await self.redis.set(key, token, nx=True, px=ttl_ms))

    async def release(self, key: str, token: str) -> None:
        await self.redis.eval(_RELEASE_LUA, 1, key, token)  # type: ignore[misc]

    async def add_spend(self, scope: str, usd: Decimal) -> None:
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.incrbyfloat(scope, float(usd))
            pipe.expire(scope, _SPEND_TTL_S)
            await pipe.execute()

    async def get_spend(self, scope: str) -> Decimal:
        raw = await self.redis.get(scope)
        return Decimal(raw) if raw else Decimal(0)


class ClickHouseWarmStore:
    def __init__(self, source: ClientSource) -> None:
        self.source = source

    async def get(self, key: str, *, allow_expired: bool = False) -> StoredPayload | None:
        sql = _GET_ANY if allow_expired else _GET_FRESH
        client = await self.source.client()
        result = await client.query(sql, parameters={"key": key})
        if not result.result_rows:
            return None
        k, provider, endpoint, payload, fetched_at, expires_at = result.result_rows[0]
        return StoredPayload(
            key=k,
            provider=provider,
            endpoint=endpoint,
            payload=json.loads(payload),
            fetched_at=_aware(fetched_at),
            expires_at=_aware(expires_at),
        )

    async def put(self, item: StoredPayload) -> None:
        client = await self.source.client()
        await client.insert(
            "provider_payloads",
            [
                [
                    item.key,
                    item.provider,
                    item.endpoint,
                    json.dumps(item.payload),
                    item.fetched_at,
                    item.expires_at,
                ]
            ],
            column_names=["key", "provider", "endpoint", "payload", "fetched_at", "expires_at"],
        )


class ClickHouseLedger:
    """Ledger rows are tiny and frequent -> ClickHouse async inserts (server-side batching)."""

    def __init__(self, source: ClientSource, *, wait: bool = False) -> None:
        self.source = source
        self.settings: dict[str, Any] = {
            "async_insert": 1,
            "wait_for_async_insert": 1 if wait else 0,
        }

    async def record(self, entry: LedgerEntry) -> None:
        client = await self.source.client()
        await client.insert(
            "provider_calls",
            [
                [
                    entry.created_at,
                    entry.provider,
                    entry.endpoint,
                    entry.cache_key,
                    entry.org_id,
                    entry.cache_tier,
                    entry.cost_usd,
                    entry.latency_ms,
                ]
            ],
            column_names=[
                "created_at",
                "provider",
                "endpoint",
                "cache_key",
                "org_id",
                "cache_tier",
                "cost_usd",
                "latency_ms",
            ],
            settings=self.settings,
        )


_KW_COLS = [
    "market",
    "keyword",
    "volume",
    "cpc",
    "competition",
    "kd",
    "intents",
    "trend",
    "trend_months",
    "serp_features",
    "source",
    "fetched_at",
]
_SERP_COLS = [
    "taken_at",
    "market",
    "keyword",
    "device",
    "positions",
    "urls",
    "domains",
    "titles",
    "features",
]


class ClickHouseKeywordStore:
    """Normalized keyword rows (`keyword_metrics`) + SERP history (`serp_snapshots`)."""

    def __init__(self, source: ClientSource) -> None:
        self.source = source

    async def save_metrics(self, rows: list[KeywordMetrics]) -> None:
        client = await self.source.client()
        await client.insert(
            "keyword_metrics",
            [
                [
                    str(m.market),
                    m.keyword,
                    m.volume,
                    m.cpc,
                    m.competition,
                    m.kd,
                    m.intents,
                    m.trend,
                    m.trend_months,
                    m.serp_features,
                    m.source,
                    m.fetched_at,
                ]
                for m in rows
            ],
            column_names=_KW_COLS,
        )

    async def save_serp(self, snap: SerpSnapshot) -> None:
        client = await self.source.client()
        await client.insert(
            "serp_snapshots",
            [
                [
                    snap.taken_at,
                    str(snap.market),
                    snap.keyword,
                    snap.device,
                    [i.position for i in snap.items],
                    [i.url for i in snap.items],
                    [i.domain for i in snap.items],
                    [i.title for i in snap.items],
                    snap.features,
                ]
            ],
            column_names=_SERP_COLS,
        )

    async def latest(self, market: Market, keywords: list[str]) -> dict[str, KeywordMetrics]:
        if not keywords:
            return {}
        client = await self.source.client()
        res = await client.query(
            f"SELECT {', '.join(_KW_COLS)} FROM keyword_metrics FINAL "  # noqa: S608 - constant
            "WHERE market = {market:String} AND keyword IN {kws:Array(String)}",
            parameters={"market": str(market), "kws": keywords},
        )
        out: dict[str, KeywordMetrics] = {}
        for row in res.result_rows:
            d = dict(zip(_KW_COLS, row, strict=True))
            d["fetched_at"] = _aware(d["fetched_at"])
            d["cpc"] = None if d["cpc"] is None else round(float(d["cpc"]), 2)
            d["competition"] = (
                None if d["competition"] is None else round(float(d["competition"]), 2)
            )
            m = KeywordMetrics.model_validate(d)
            out[m.keyword] = m
        return out


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
