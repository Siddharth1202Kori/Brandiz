"""Pure mappers: DataForSEO JSON -> normalized models. No I/O, fully fixture-tested.

Rule: a value DataForSEO does not report becomes None, never 0 (0 volume != unknown).
"""

from datetime import datetime
from typing import Any

from seomaster_core.keywords import InvalidKeywordError, normalize_keyword
from seomaster_core.markets import Market
from seomaster_core.seo import KeywordMetrics, SerpItem, SerpSnapshot

SOURCE_LABS = "dataforseo_labs"
SOURCE_ADS = "google_ads"
TREND_MONTHS = 12


def _int(v: Any) -> int | None:
    return None if v is None else round(float(v))


def _float(v: Any, ndigits: int = 2) -> float | None:
    return None if v is None else round(float(v), ndigits)


def trend(monthly: list[dict[str, Any]] | None) -> tuple[list[int | None], list[str]]:
    """monthly_searches (newest first) -> last 12 months oldest->newest, plus YYYY-MM labels."""
    rows = sorted(
        (m for m in monthly or [] if m.get("year") and m.get("month")),
        key=lambda m: (m["year"], m["month"]),
    )[-TREND_MONTHS:]
    return [_int(m.get("search_volume")) for m in rows], [
        f"{m['year']:04d}-{m['month']:02d}" for m in rows
    ]


def intents(info: dict[str, Any] | None) -> list[str]:
    if not info:
        return []
    out = [info["main_intent"]] if info.get("main_intent") else []
    out += [i for i in info.get("foreign_intent") or [] if i and i not in out]
    return out


def keyword_item(item: dict[str, Any], market: Market, fetched_at: datetime) -> KeywordMetrics:
    """Labs item (keyword_overview / keyword_ideas / keyword_suggestions / related.keyword_data)."""
    info = item.get("keyword_info") or {}
    props = item.get("keyword_properties") or {}
    serp = item.get("serp_info") or {}
    values, months = trend(info.get("monthly_searches"))
    return KeywordMetrics(
        keyword=normalize_keyword(item["keyword"]),
        market=market,
        volume=_int(info.get("search_volume")),
        cpc=_float(info.get("cpc")),
        competition=_float(info.get("competition")),
        kd=_int(props.get("keyword_difficulty")),
        intents=intents(item.get("search_intent_info")),
        trend=values,
        trend_months=months,
        serp_features=[t for t in serp.get("serp_item_types") or [] if t != "organic"],
        source=SOURCE_LABS,
        fetched_at=fetched_at,
    )


def empty_metrics(kw: str, market: Market, fetched_at: datetime) -> KeywordMetrics:
    """No data for this keyword in this market: every metric unknown."""
    return KeywordMetrics(keyword=kw, market=market, source=SOURCE_LABS, fetched_at=fetched_at)


def keyword_items(
    items: list[dict[str, Any]] | None, market: Market, fetched_at: datetime
) -> list[KeywordMetrics]:
    """Normalizes a result list, unwrapping related_keywords' `keyword_data`; dedupes by keyword."""
    seen: set[str] = set()
    out: list[KeywordMetrics] = []
    for raw in items or []:
        item = raw.get("keyword_data", raw)
        if not item.get("keyword"):
            continue
        try:
            m = keyword_item(item, market, fetched_at)
        except InvalidKeywordError:
            continue
        if m.keyword not in seen:
            seen.add(m.keyword)
            out.append(m)
    return out


def serp_snapshot(
    result: dict[str, Any], kw: str, market: Market, taken_at: datetime, depth: int = 10
) -> SerpSnapshot:
    organic = sorted(
        (i for i in result.get("items") or [] if i.get("type") == "organic" and i.get("url")),
        key=lambda i: int(i.get("rank_group") or 0),
    )[:depth]
    return SerpSnapshot(
        keyword=kw,
        market=market,
        items=[
            SerpItem(
                position=int(i.get("rank_group") or n),
                url=i["url"],
                domain=i.get("domain") or "",
                title=i.get("title"),
            )
            for n, i in enumerate(organic, start=1)
        ],
        features=sorted({t for t in result.get("item_types") or [] if t != "organic"}),
        taken_at=taken_at,
    )


def ads_volume_item(item: dict[str, Any], market: Market, fetched_at: datetime) -> KeywordMetrics:
    """Google Ads search_volume task_get result row (flat: keyword, search_volume, cpc, ...)."""
    values, months = trend(item.get("monthly_searches"))
    competition = item.get("competition_index")
    return KeywordMetrics(
        keyword=normalize_keyword(item["keyword"]),
        market=market,
        volume=_int(item.get("search_volume")),
        cpc=_float(item.get("cpc")),
        competition=None if competition is None else round(float(competition) / 100, 2),
        trend=values,
        trend_months=months,
        source=SOURCE_ADS,
        fetched_at=fetched_at,
    )


def difficulty_map(items: list[dict[str, Any]] | None) -> dict[str, int | None]:
    return {
        normalize_keyword(i["keyword"]): _int(i.get("keyword_difficulty"))
        for i in items or []
        if i.get("keyword")
    }


def intent_map(items: list[dict[str, Any]] | None) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for i in items or []:
        if not i.get("keyword"):
            continue
        labels = [(i.get("keyword_intent") or {}).get("label")]
        labels += [s.get("label") for s in i.get("secondary_keyword_intents") or []]
        out[normalize_keyword(i["keyword"])] = [lbl for lbl in labels if lbl]
    return out
