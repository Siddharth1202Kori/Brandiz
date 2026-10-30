"""/api/v1/admin — provider cost + cache dashboard (reads the ClickHouse `provider_calls` ledger).

"Views" = DAL lookups (every report load). Hit rate = share answered from cache.
Cost per view = provider spend / views: what one report load costs us on average.
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from seomaster_api.deps import require_admin
from seomaster_core.models import Envelope

router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class EndpointUsage(BaseModel):
    provider: str
    endpoint: str
    views: int
    cache_hits: int
    provider_calls: int
    hit_rate: float
    cost_usd: float
    cost_per_view_usd: float
    avg_latency_ms: float


class DayUsage(BaseModel):
    day: str
    views: int
    hit_rate: float
    cost_usd: float


class RecentCall(BaseModel):
    created_at: datetime
    provider: str
    endpoint: str
    cache_key: str
    cache_tier: str
    cost_usd: float
    latency_ms: int


class UsageOut(BaseModel):
    days: int
    views: int
    hit_rate: float
    cost_usd: float
    cost_per_view_usd: float
    by_endpoint: list[EndpointUsage]
    by_day: list[DayUsage]
    recent: list[RecentCall]


def _rate(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0.0


@router.get("/usage")
async def usage(
    request: Request, days: Annotated[int, Query(ge=1, le=90)] = 7
) -> Envelope[UsageOut]:
    client = await request.app.state.clickhouse.client()
    params = {"days": days}
    ep = await client.query(
        "SELECT provider, endpoint, count(), countIf(cache_tier != 'provider'), "
        "countIf(cache_tier = 'provider'), sum(cost_usd), avg(latency_ms) "
        "FROM provider_calls WHERE created_at >= now64(3) - toIntervalDay({days:UInt16}) "
        "GROUP BY provider, endpoint ORDER BY sum(cost_usd) DESC, count() DESC",
        parameters=params,
    )
    by_endpoint = [
        EndpointUsage(
            provider=p,
            endpoint=e,
            views=v,
            cache_hits=h,
            provider_calls=c,
            hit_rate=_rate(h, v),
            cost_usd=float(cost),
            cost_per_view_usd=round(float(cost) / v, 6) if v else 0.0,
            avg_latency_ms=round(float(lat), 1),
        )
        for p, e, v, h, c, cost, lat in ep.result_rows
    ]
    daily = await client.query(
        "SELECT toString(toDate(created_at)) AS d, count(), countIf(cache_tier != 'provider'), "
        "sum(cost_usd) FROM provider_calls "
        "WHERE created_at >= now64(3) - toIntervalDay({days:UInt16}) "
        "GROUP BY d ORDER BY d",
        parameters=params,
    )
    recent = await client.query(
        "SELECT created_at, provider, endpoint, cache_key, cache_tier, cost_usd, latency_ms "
        "FROM provider_calls ORDER BY created_at DESC LIMIT 25"
    )
    views = sum(x.views for x in by_endpoint)
    hits = sum(x.cache_hits for x in by_endpoint)
    cost = sum(x.cost_usd for x in by_endpoint)
    return Envelope(
        data=UsageOut(
            days=days,
            views=views,
            hit_rate=_rate(hits, views),
            cost_usd=round(cost, 6),
            cost_per_view_usd=round(cost / views, 6) if views else 0.0,
            by_endpoint=by_endpoint,
            by_day=[
                DayUsage(day=d, views=v, hit_rate=_rate(h, v), cost_usd=float(c))
                for d, v, h, c in daily.result_rows
            ],
            recent=[
                RecentCall.model_validate(dict(zip(recent.column_names, r, strict=True)))
                for r in recent.result_rows
            ],
        )
    )
