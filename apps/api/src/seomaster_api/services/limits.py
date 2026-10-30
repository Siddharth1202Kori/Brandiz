"""Plan limits + metering (Semrush analogue: limit payloads fetched by every tool, doc 02).

Metered metrics live in `usage_counters` keyed by period. Count metrics (projects, ...) are
computed from their own tables. Caps (`ideas_rows_per_report`) are plain plan values.

A report is charged once per org per day: re-opening, re-sorting or paging the same report
is free. Idea rows are charged by high-water mark (rows already seen today are free).
"""

import contextlib
from datetime import UTC, datetime
from typing import Literal

from redis.asyncio import Redis
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from seomaster_api.errors import AppError, QuotaExceededError
from seomaster_db.models import KeywordList, Org, Plan, Project, UsageCounter

Period = Literal["day", "month", "total"]

METERED: dict[str, Period] = {
    "reports_per_day": "day",
    "keyword_ideas_rows": "day",
    "exports_per_day": "day",
    "audit_pages": "month",
}
COUNTED: dict[str, Period] = {
    "projects": "total",
    "keyword_lists": "total",
    "rank_keywords": "total",
    "gsc_sites": "total",
}

_CONSUME_SQL = text(
    """
    INSERT INTO usage_counters (org_id, metric, period, used)
    SELECT CAST(:org_id AS uuid), CAST(:metric AS varchar), CAST(:period AS varchar),
           CAST(:n AS bigint)
    WHERE CAST(:n AS bigint) <= CAST(:max AS bigint)
    ON CONFLICT (org_id, metric, period)
    DO UPDATE SET used = usage_counters.used + EXCLUDED.used
    WHERE usage_counters.used + EXCLUDED.used <= CAST(:max AS bigint)
    RETURNING used
    """
)


def period_key(period: Period, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    if period == "day":
        return now.strftime("%Y-%m-%d")
    if period == "month":
        return now.strftime("%Y-%m")
    return "total"


async def plan_limits(db: AsyncSession, org: Org) -> dict[str, int]:
    plan = await db.get(Plan, org.plan_id)
    if plan is None:
        raise AppError(500, "plan_missing", f"Unknown plan {org.plan_id}")
    return {k: int(v) for k, v in plan.limits.items()}


async def consume(
    db: AsyncSession, org: Org, metric: str, amount: int = 1, now: datetime | None = None
) -> int:
    """Atomically add `amount` unless it would exceed the plan limit. Returns new usage.

    Single statement -> safe under concurrency without explicit locks.
    """
    if metric not in METERED:
        raise ValueError(f"{metric} is not a metered metric")
    limit = (await plan_limits(db, org)).get(metric, 0)
    used = await db.scalar(
        _CONSUME_SQL,
        {
            "org_id": org.id,
            "metric": metric,
            "period": period_key(METERED[metric], now),
            "n": amount,
            "max": limit,
        },
    )
    if used is None:
        raise QuotaExceededError(metric, limit)
    return int(used)


async def consume_up_to(
    db: AsyncSession, org: Org, metric: str, amount: int, now: datetime | None = None
) -> int:
    """Grants as much of `amount` as the plan allows (maybe 0). Caller commits.

    Row lock (`FOR UPDATE`) keeps concurrent requests from over-granting.
    """
    if metric not in METERED:
        raise ValueError(f"{metric} is not a metered metric")
    if amount <= 0:
        return 0
    limit = (await plan_limits(db, org)).get(metric, 0)
    period = period_key(METERED[metric], now)
    await db.execute(
        pg_insert(UsageCounter)
        .values(org_id=org.id, metric=metric, period=period, used=0)
        .on_conflict_do_nothing()
    )
    where = (
        UsageCounter.org_id == org.id,
        UsageCounter.metric == metric,
        UsageCounter.period == period,
    )
    used = int(await db.scalar(select(UsageCounter.used).where(*where).with_for_update()) or 0)
    granted = max(0, min(amount, limit - used))
    if granted:
        await db.execute(update(UsageCounter).where(*where).values(used=used + granted))
    return granted


async def cap(db: AsyncSession, org: Org, name: str) -> int:
    return (await plan_limits(db, org)).get(name, 0)


_SEEN_TTL_S = 2 * 24 * 3600


async def charge_report(db: AsyncSession, redis: Redis, org: Org, report_key: str) -> None:
    """Consumes 1 `reports_per_day` the first time today this org opens `report_key`."""
    seen = f"report-seen:{org.id}:{period_key('day')}:{report_key}"
    try:
        first = bool(await redis.set(seen, "1", nx=True, ex=_SEEN_TTL_S))
    except Exception:
        first = True  # Redis down: charge rather than give reports away
    if not first:
        return
    try:
        await consume(db, org, "reports_per_day")
        await db.commit()
    except BaseException:
        await db.rollback()
        with contextlib.suppress(Exception):  # key just expires in 2 days otherwise
            await redis.delete(seen)
        raise


async def charge_rows(db: AsyncSession, redis: Redis, org: Org, report_key: str, end: int) -> int:
    """Charges idea rows up to position `end`; returns how far the org may actually see."""
    seen_key = f"rows-seen:{org.id}:{period_key('day')}:{report_key}"
    try:
        seen = int(await redis.get(seen_key) or 0)
    except Exception:
        seen = 0
    if end <= seen:
        return end
    granted = await consume_up_to(db, org, "keyword_ideas_rows", end - seen)
    await db.commit()
    reached = seen + granted
    with contextlib.suppress(Exception):  # worst case the next page re-charges these rows
        await redis.set(seen_key, reached, ex=_SEEN_TTL_S)
    return reached


async def count_used(db: AsyncSession, org: Org, metric: str) -> int:
    if metric == "projects":
        return int(await db.scalar(select(func.count()).where(Project.org_id == org.id)) or 0)
    if metric == "keyword_lists":
        q = select(func.count()).where(KeywordList.org_id == org.id)
        return int(await db.scalar(q) or 0)
    return 0  # rank_keywords (Phase 5), gsc_sites (Phase 4)


async def check_count(db: AsyncSession, org: Org, metric: str) -> None:
    limit = (await plan_limits(db, org)).get(metric, 0)
    if await count_used(db, org, metric) >= limit:
        raise QuotaExceededError(metric, limit)


async def snapshot(db: AsyncSession, org: Org) -> list[dict[str, object]]:
    limits = await plan_limits(db, org)
    rows = []
    for metric, period in {**METERED, **COUNTED}.items():
        if metric in METERED:
            used = await db.scalar(
                select(UsageCounter.used).where(
                    UsageCounter.org_id == org.id,
                    UsageCounter.metric == metric,
                    UsageCounter.period == period_key(period),
                )
            )
        else:
            used = await count_used(db, org, metric)
        rows.append(
            {"name": metric, "used": int(used or 0), "max": limits.get(metric, 0), "period": period}
        )
    return rows
