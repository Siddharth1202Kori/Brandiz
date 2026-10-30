"""/api/v1/keywords — Keyword Overview, SERP preview, Keyword Magic (ideas) and CSV export.

Metering: each report costs 1 `reports_per_day` the first time an org opens it on a given
day (overview + SERP of the same keyword count as one report). Ideas rows are charged by
high-water mark against `keyword_ideas_rows` and capped by `ideas_rows_per_report`.
"""

import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from seomaster_api.deps import DB, CurrentOrg, Keywords, RedisDep
from seomaster_api.errors import AppError
from seomaster_api.services import limits
from seomaster_api.services.keyword_filters import IdeaFilters, SortDir, SortField, apply
from seomaster_core.keywords import InvalidKeywordError, normalize_keyword
from seomaster_core.markets import Market
from seomaster_core.models import Envelope, Meta, PageInfo
from seomaster_core.seo import KeywordMetrics, SerpSnapshot
from seomaster_providers.dal import DalResult
from seomaster_providers.interfaces import IdeasMode

router = APIRouter(prefix="/api/v1/keywords", tags=["keywords"])

CSV_COLUMNS = ["keyword", "volume", "kd", "cpc", "competition", "intents", "serp_features"]


def keyword_param(raw: str) -> str:
    try:
        return normalize_keyword(raw)
    except InvalidKeywordError as exc:
        raise AppError(422, "invalid_keyword", str(exc)) from exc


def _meta(res: DalResult, **extra: object) -> Meta:
    return Meta(
        cached=res.cached, stale=res.stale, source=res.source, fetched_at=res.fetched_at, **extra
    )


def idea_filters(
    volume_min: int | None = Query(None, ge=0),
    volume_max: int | None = Query(None, ge=0),
    kd_min: int | None = Query(None, ge=0, le=100),
    kd_max: int | None = Query(None, ge=0, le=100),
    cpc_min: float | None = Query(None, ge=0),
    cpc_max: float | None = Query(None, ge=0),
    words_min: int | None = Query(None, ge=1),
    words_max: int | None = Query(None, ge=1),
    intent: Annotated[list[str] | None, Query()] = None,
    include: Annotated[list[str] | None, Query()] = None,
    exclude: Annotated[list[str] | None, Query()] = None,
) -> IdeaFilters:
    return IdeaFilters(
        volume_min=volume_min,
        volume_max=volume_max,
        kd_min=kd_min,
        kd_max=kd_max,
        cpc_min=cpc_min,
        cpc_max=cpc_max,
        words_min=words_min,
        words_max=words_max,
        intents=intent or [],
        include=include or [],
        exclude=exclude or [],
    )


Filters = Annotated[IdeaFilters, Depends(idea_filters)]


@router.get("/overview")
async def overview(
    q: str, db: DB, redis: RedisDep, org: CurrentOrg, kw: Keywords, market: Market = Market.IN
) -> Envelope[KeywordMetrics]:
    keyword = keyword_param(q)
    await limits.charge_report(db, redis, org, f"overview:{market}:{keyword}")
    report = await kw.overview(keyword, market, org.id)
    return Envelope(data=report.data, meta=_meta(report.result))


@router.get("/serp")
async def serp(
    q: str, db: DB, redis: RedisDep, org: CurrentOrg, kw: Keywords, market: Market = Market.IN
) -> Envelope[SerpSnapshot]:
    keyword = keyword_param(q)
    await limits.charge_report(db, redis, org, f"overview:{market}:{keyword}")
    report = await kw.serp(keyword, market, org.id)
    return Envelope(data=report.data, meta=_meta(report.result))


@router.get("/ideas")
async def ideas(
    seed: str,
    db: DB,
    redis: RedisDep,
    org: CurrentOrg,
    kw: Keywords,
    filters: Filters,
    market: Market = Market.IN,
    mode: IdeasMode = "ideas",
    sort: SortField = "volume",
    dir: SortDir = "desc",
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> Envelope[list[KeywordMetrics]]:
    phrase = keyword_param(seed)
    report_key = f"ideas:{market}:{mode}:{phrase}"
    await limits.charge_report(db, redis, org, report_key)
    report = await kw.ideas(phrase, market, mode, org.id)

    rows = apply(report.data, filters, sort, dir)
    visible = min(len(rows), await limits.cap(db, org, "ideas_rows_per_report"))
    end = min(offset + limit, visible)
    allowed = await limits.charge_rows(db, redis, org, report_key, end) if end > offset else end
    page = rows[offset : min(end, allowed)]
    limited = len(rows) > visible or allowed < end
    return Envelope(
        data=page,
        meta=_meta(
            report.result,
            limited=limited,
            page=PageInfo(offset=offset, limit=limit, total=len(rows)),
        ),
    )


@router.get("/ideas/export.csv", response_class=Response)
async def export_ideas(
    seed: str,
    db: DB,
    redis: RedisDep,
    org: CurrentOrg,
    kw: Keywords,
    filters: Filters,
    market: Market = Market.IN,
    mode: IdeasMode = "ideas",
    sort: SortField = "volume",
    dir: SortDir = "desc",
) -> Response:
    phrase = keyword_param(seed)
    await limits.consume(db, org, "exports_per_day")
    await db.commit()
    await limits.charge_report(db, redis, org, f"ideas:{market}:{mode}:{phrase}")
    report = await kw.ideas(phrase, market, mode, org.id)
    rows = apply(report.data, filters, sort, dir)
    rows = rows[: await limits.cap(db, org, "ideas_rows_per_report")]
    return csv_response(rows, f"brandiz-{mode}-{market}-{phrase.replace(' ', '-')}.csv")


def _cell(value: object) -> str:
    """Neutralizes spreadsheet formula injection (cells starting with = + - @)."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def csv_rows(rows: list[KeywordMetrics]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for m in rows:
        w.writerow(
            [
                _cell(m.keyword),
                _cell(m.volume),
                _cell(m.kd),
                _cell(m.cpc),
                _cell(m.competition),
                _cell("|".join(m.intents)),
                _cell("|".join(m.serp_features)),
            ]
        )
    return buf.getvalue()


def csv_response(rows: list[KeywordMetrics], filename: str) -> Response:
    # headers are latin-1: keep ASCII only (Hindi keywords would otherwise break the header)
    safe = "".join(c for c in filename if c.isascii() and (c.isalnum() or c in "-_."))
    safe = safe if safe.removesuffix(".csv").strip("-_.") else "brandiz-export.csv"
    return Response(
        content=csv_rows(rows),
        media_type="text/csv; charset=utf-8",
        headers={"content-disposition": f'attachment; filename="{safe}"'},
    )
