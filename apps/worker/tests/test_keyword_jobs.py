"""Keyword jobs end to end on the fake provider + real test datastores (docker)."""

import os

os.environ.update(
    APP_ENV="test",
    DATABASE_URL="postgresql+asyncpg://seomaster:seomaster@localhost:5432/seomaster_test",
    REDIS_URL="redis://localhost:6379/15",
    CLICKHOUSE_DATABASE="seomaster_test",
)

import time
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from seomaster_core.config import Settings
from seomaster_core.markets import Market
from seomaster_db.base import Base, make_engine
from seomaster_db.clickhouse import migrate
from seomaster_db.models import KeywordList, KeywordListItem, Org, Plan
from seomaster_db.seed import PLANS
from seomaster_worker import keyword_jobs

pytestmark = pytest.mark.integration


@pytest.fixture
async def rt() -> AsyncIterator[keyword_jobs.Runtime]:
    settings = Settings()
    engine = make_engine(settings.database_url)
    async with engine.begin() as conn:  # idempotent: API tests may have created these already
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(pg_insert(Plan).values(PLANS).on_conflict_do_nothing())
    await engine.dispose()
    await migrate(settings)
    async with keyword_jobs.runtime(settings) as runtime:
        yield runtime


async def make_list(rt: keyword_jobs.Runtime, keywords: list[str]) -> uuid.UUID:
    async with rt.sessions() as db:
        org = Org(name="jobs", plan_id="free")
        db.add(org)
        await db.flush()
        kl = KeywordList(org_id=org.id, name=f"l{uuid.uuid4().hex[:6]}", market="us")
        db.add(kl)
        await db.flush()
        db.add_all(KeywordListItem(list_id=kl.id, keyword=k, intents=[]) for k in keywords)
        await db.commit()
        return kl.id


async def items(rt: keyword_jobs.Runtime, list_id: uuid.UUID) -> dict[str, KeywordListItem]:
    async with rt.sessions() as db:
        rows = await db.scalars(select(KeywordListItem).where(KeywordListItem.list_id == list_id))
        return {i.keyword: i for i in rows}


async def test_volume_batch_fills_list_items(rt: keyword_jobs.Runtime) -> None:
    tag = time.time_ns()
    keywords = [f"job kw {tag} a", f"job kw {tag} b"]
    list_id = await make_list(rt, keywords)

    queued = await keyword_jobs.queue_volume_batch(rt)
    assert queued, "expected a volume task"
    after_queue = await items(rt, list_id)
    assert all(after_queue[k].kd is not None for k in keywords)  # KD/intent filled right away
    assert all(after_queue[k].volume is None for k in keywords)  # volume waits for the task

    # A second run while the task is in flight must not re-post the same keywords
    for task_id, _ in await keyword_jobs.queue_volume_batch(rt):
        posted = await rt.redis.get(f"volume-task:{task_id}") or ""
        assert keywords[0] not in posted

    for task_id, market in queued:
        assert await keyword_jobs.collect_volume(rt, task_id, market) is not None

    done = await items(rt, list_id)
    for k in keywords:
        assert done[k].volume is not None and done[k].metrics_updated_at is not None
        assert done[k].kd is not None  # kept from the KD step
    latest = await rt.keywords.store.latest(Market.US, keywords)
    assert set(latest) == set(keywords)


async def test_refresh_reloads_recently_viewed_keywords(
    rt: keyword_jobs.Runtime, monkeypatch: pytest.MonkeyPatch
) -> None:
    kw = f"refresh me {time.time_ns()}"
    await rt.keywords.overview(kw, Market.US, None)  # a "view": ledger row + cached payload
    monkeypatch.setattr(keyword_jobs, "REFRESH_EXPIRING_DAYS", 40)  # treat 30-day TTL as expiring

    refreshed = await keyword_jobs.refresh_stale_keywords(rt, max_keywords=1000)
    assert refreshed >= 1
    client = await rt.clickhouse.client()
    res = await client.query(
        "SELECT count() FROM provider_calls "
        "WHERE cache_key = {k:String} AND cache_tier = 'provider'",
        parameters={"k": f"kw:fake:us:{kw}"},
    )
    assert res.result_rows[0][0] == 2  # original fetch + forced refresh
