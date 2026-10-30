"""Keyword background jobs (async core; Celery wrappers live in `tasks.py`).

refresh_stale_keywords  nightly: re-fetch overviews viewed in the last 7 days that expire soon,
                        so popular keywords never go cold for users.
queue_volume_batch      every 15 min: list items without fresh metrics -> KD + intent (live)
                        and a queued Google Ads volume task (cheaper than live).
collect_volume          polls that queued task and writes volume/CPC onto list items.

Every paid call goes through the DAL (budget guard + ledger), like report traffic.
"""

import hashlib
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from seomaster_core.config import Settings
from seomaster_core.markets import Market
from seomaster_core.seo import KeywordMetrics
from seomaster_db.base import make_engine, make_sessionmaker
from seomaster_db.clickhouse import ClickHouseHandle
from seomaster_db.models import KeywordList, KeywordListItem
from seomaster_providers.dal import DalRequest, FetchResult
from seomaster_providers.factory import (
    build_keyword_provider,
    build_keyword_service,
    close_provider,
)
from seomaster_providers.interfaces import Priced
from seomaster_providers.keywords import KeywordService

log = logging.getLogger(__name__)

REFRESH_VIEWED_DAYS = 7
REFRESH_EXPIRING_DAYS = 3
REFRESH_MAX_PER_RUN = 50  # ~$0.50/night on DataForSEO Labs; raise once traffic justifies it
METRICS_STALE_DAYS = 30
VOLUME_BATCH_SIZE = 1000  # Google Ads task maximum
PENDING_TTL_S = 6 * 3600


@dataclass
class Runtime:
    sessions: async_sessionmaker[AsyncSession]
    redis: Redis
    clickhouse: ClickHouseHandle
    keywords: KeywordService


@asynccontextmanager
async def runtime(settings: Settings) -> AsyncIterator[Runtime]:
    engine = make_engine(settings.database_url)
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)
    clickhouse = ClickHouseHandle(settings)
    provider = build_keyword_provider(settings)
    try:
        yield Runtime(
            sessions=make_sessionmaker(engine),
            redis=redis,
            clickhouse=clickhouse,
            keywords=build_keyword_service(settings, redis, clickhouse, provider),
        )
    finally:
        await close_provider(provider)
        await clickhouse.close()
        await redis.aclose()
        await engine.dispose()


# -- nightly refresh --------------------------------------------------------------------------


async def refresh_stale_keywords(rt: Runtime, *, max_keywords: int = REFRESH_MAX_PER_RUN) -> int:
    provider = rt.keywords.provider.name
    client = await rt.clickhouse.client()
    res = await client.query(
        "SELECT key FROM provider_payloads FINAL "
        "WHERE key IN ("
        "  SELECT DISTINCT cache_key FROM provider_calls"
        "  WHERE endpoint = 'keyword.overview'"
        "    AND created_at >= now64(3) - toIntervalDay({viewed:UInt16})"
        "    AND startsWith(cache_key, {prefix:String})"
        ") AND expires_at < now64(3) + toIntervalDay({expiring:UInt16}) "
        "ORDER BY expires_at LIMIT {n:UInt32}",
        parameters={
            "viewed": REFRESH_VIEWED_DAYS,
            "expiring": REFRESH_EXPIRING_DAYS,
            "prefix": f"kw:{provider}:",
            "n": max_keywords,
        },
    )
    done = 0
    for (key,) in res.result_rows:
        _, _, market, kw = key.split(":", 3)
        try:
            await rt.keywords.overview(kw, Market(market), None, force=True)
            done += 1
        except Exception:
            log.exception("refresh failed for %s", key)
    log.info("refreshed %d stale keywords", done)
    return done


# -- list item metrics ------------------------------------------------------------------------


async def _via_dal(
    rt: Runtime,
    key: str,
    endpoint: str,
    ttl: timedelta,
    call: Callable[[], Awaitable[Priced[Any]]],
) -> Any:
    async def fetch() -> FetchResult:
        priced = await call()
        return FetchResult(priced.value, priced.cost_usd)

    req = DalRequest(key=key, ttl=ttl, provider=rt.keywords.provider.name, endpoint=endpoint)
    return (await rt.keywords.dal.get(req, fetch)).payload


def _digest(keywords: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(keywords)).encode()).hexdigest()[:16]


async def _stale_keywords(db: AsyncSession) -> dict[Market, list[str]]:
    cutoff = datetime.now(UTC) - timedelta(days=METRICS_STALE_DAYS)
    rows = await db.execute(
        select(KeywordList.market, KeywordListItem.keyword)
        .join(KeywordList, KeywordList.id == KeywordListItem.list_id)
        .where(
            or_(
                KeywordListItem.metrics_updated_at.is_(None),
                KeywordListItem.metrics_updated_at < cutoff,
            )
        )
        .distinct()
        .limit(VOLUME_BATCH_SIZE * len(Market))
    )
    out: dict[Market, list[str]] = {}
    for market, kw in rows.all():
        out.setdefault(Market(market), []).append(kw)
    return out


async def _claim(redis: Redis, market: Market, keywords: list[str]) -> list[str]:
    """Skips keywords already in an in-flight volume task."""
    async with redis.pipeline(transaction=False) as pipe:
        for kw in keywords:
            pipe.set(f"volume-pending:{market}:{kw}", "1", nx=True, ex=PENDING_TTL_S)
        claimed = await pipe.execute()
    return [kw for kw, ok in zip(keywords, claimed, strict=True) if ok]


async def _update_items(
    db: AsyncSession, market: Market, values: dict[str, dict[str, Any]]
) -> None:
    lists = select(KeywordList.id).where(KeywordList.market == market.value)
    for kw, fields in values.items():
        await db.execute(
            update(KeywordListItem)
            .where(KeywordListItem.keyword == kw, KeywordListItem.list_id.in_(lists))
            .values(**fields)
        )


async def queue_volume_batch(rt: Runtime) -> list[tuple[str, str]]:
    """Returns (task_id, market) pairs to collect later."""
    provider = rt.keywords.provider
    async with rt.sessions() as db:
        stale = await _stale_keywords(db)
    queued: list[tuple[str, str]] = []
    for market, candidates in stale.items():
        keywords = (await _claim(rt.redis, market, candidates))[:VOLUME_BATCH_SIZE]
        if not keywords:
            continue
        digest = _digest(keywords)

        def kd_call(m: Market = market, k: list[str] = keywords) -> Awaitable[Priced[Any]]:
            return provider.difficulty(k, m)

        def intent_call(m: Market = market, k: list[str] = keywords) -> Awaitable[Priced[Any]]:
            return provider.intents(k, m)

        def volume_call(m: Market = market, k: list[str] = keywords) -> Awaitable[Priced[Any]]:
            return provider.post_volume_task(k, m)

        week = timedelta(days=7)
        kd: dict[str, int | None] = await _via_dal(
            rt, f"kd:{provider.name}:{market}:{digest}", "keyword.difficulty", week, kd_call
        )
        intents: dict[str, list[str]] = await _via_dal(
            rt, f"intent:{provider.name}:{market}:{digest}", "keyword.intent", week, intent_call
        )
        async with rt.sessions() as db:
            await _update_items(
                db,
                market,
                {k: {"kd": kd.get(k), "intents": intents.get(k, [])} for k in keywords},
            )
            await db.commit()
        task_id: str = await _via_dal(
            rt,
            f"volume-task:{provider.name}:{market}:{digest}",
            "keyword.volume_task",
            timedelta(minutes=1),
            volume_call,
        )
        await rt.redis.set(f"volume-task:{task_id}", json.dumps(keywords), ex=24 * 3600)
        queued.append((task_id, market.value))
        log.info("queued volume task %s for %d %s keywords", task_id, len(keywords), market)
    return queued


async def collect_volume(rt: Runtime, task_id: str, market_code: str) -> int | None:
    """Writes results onto list items. Returns rows updated, or None if not ready yet."""
    market = Market(market_code)
    results = await rt.keywords.provider.get_volume_task(task_id, market)
    if results is None:
        return None
    raw = await rt.redis.get(f"volume-task:{task_id}")
    posted: list[str] = json.loads(raw) if raw else [m.keyword for m in results]
    by_kw = {m.keyword: m for m in results}
    now = datetime.now(UTC)

    try:
        known = await rt.keywords.store.latest(market, list(by_kw))
        await rt.keywords.store.save_metrics([_merge(known.get(k), m) for k, m in by_kw.items()])
    except Exception:
        log.exception("keyword_metrics merge/write failed")

    values: dict[str, dict[str, Any]] = {}
    for kw in posted:  # no result = no data; stamp it anyway so it isn't retried every run
        m = by_kw.get(kw)
        values[kw] = {"metrics_updated_at": now, "source": m.source if m else None}
        if m:
            values[kw] |= {"volume": m.volume, "cpc": m.cpc, "competition": m.competition}
    async with rt.sessions() as db:
        await _update_items(db, market, values)
        await db.commit()
    pending = [f"volume-pending:{market}:{k}" for k in posted]
    await rt.redis.delete(f"volume-task:{task_id}", *pending)
    return len(values)


def _merge(old: KeywordMetrics | None, new: KeywordMetrics) -> KeywordMetrics:
    """Ads gives volume/CPC; keep Labs-only fields (KD, intent, SERP features) we already had."""
    if old is None:
        return new
    return new.model_copy(
        update={
            "kd": old.kd,
            "intents": old.intents,
            "serp_features": old.serp_features,
            "trend": new.trend or old.trend,
            "trend_months": new.trend_months or old.trend_months,
        }
    )
