"""DataForSEO keyword adapter (implements `KeywordProvider`).

Endpoints (v3): Labs for overview/ideas/KD/intent (one consistent volume source), SERP API for
the top-10 preview, Google Ads queued tasks for cheap bulk volume refresh of list items.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from seomaster_core.markets import Market
from seomaster_core.seo import KeywordMetrics, SerpSnapshot
from seomaster_providers.dataforseo import normalize as n
from seomaster_providers.dataforseo.client import DataForSEOClient
from seomaster_providers.interfaces import IdeasMode, Priced

LABS = "dataforseo_labs/google"
PATHS = {
    "overview": f"{LABS}/keyword_overview/live",
    "ideas": f"{LABS}/keyword_ideas/live",
    "related": f"{LABS}/related_keywords/live",
    "suggestions": f"{LABS}/keyword_suggestions/live",
    "difficulty": f"{LABS}/bulk_keyword_difficulty/live",
    "intents": f"{LABS}/search_intent/live",
    "serp": "serp/google/organic/live/advanced",
    "volume_post": "keywords_data/google_ads/search_volume/task_post",
    "volume_get": "keywords_data/google_ads/search_volume/task_get",
}
MAX_BULK = 1000  # Labs bulk + Google Ads accept up to 1000 keywords per task
SERP_DEPTH = 10


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DataForSEOKeywordProvider:
    name = "dataforseo"

    def __init__(self, client: DataForSEOClient, now: Callable[[], datetime] = _utcnow) -> None:
        self.client = client
        self.now = now

    @staticmethod
    def _geo(market: Market) -> dict[str, Any]:
        return {"location_code": market.location_code, "language_code": market.language_code}

    async def overview(self, kw: str, market: Market) -> Priced[KeywordMetrics]:
        task = await self.client.post(
            PATHS["overview"], {"keywords": [kw], **self._geo(market), "include_serp_info": True}
        )
        now = self.now()
        items = n.keyword_items(task.first.get("items"), market, now)
        hit = next((m for m in items if m.keyword == kw), None)
        return Priced(hit or n.empty_metrics(kw, market, now), task.cost)

    async def ideas(
        self, seed: str, market: Market, mode: IdeasMode, limit: int
    ) -> Priced[list[KeywordMetrics]]:
        common = {**self._geo(market), "limit": limit, "include_serp_info": True}
        if mode == "ideas":
            body = {
                "keywords": [seed],
                **common,
                "order_by": ["keyword_info.search_volume,desc"],
            }
        elif mode == "related":
            body = {
                "keyword": seed,
                "depth": 2,
                **common,
                "order_by": ["keyword_data.keyword_info.search_volume,desc"],
            }
        else:
            body = {"keyword": seed, **common, "order_by": ["keyword_info.search_volume,desc"]}
        task = await self.client.post(PATHS[mode], body)
        return Priced(n.keyword_items(task.first.get("items"), market, self.now()), task.cost)

    async def serp(self, kw: str, market: Market) -> Priced[SerpSnapshot]:
        task = await self.client.post(
            PATHS["serp"],
            {"keyword": kw, **self._geo(market), "device": "desktop", "depth": SERP_DEPTH},
        )
        return Priced(n.serp_snapshot(task.first, kw, market, self.now(), SERP_DEPTH), task.cost)

    async def difficulty(
        self, keywords: list[str], market: Market
    ) -> Priced[dict[str, int | None]]:
        total, out = Decimal(0), {}
        for chunk in _chunks(keywords):
            task = await self.client.post(
                PATHS["difficulty"], {"keywords": chunk, **self._geo(market)}
            )
            total += task.cost
            out.update(n.difficulty_map(task.first.get("items")))
        return Priced(out, total)

    async def intents(self, keywords: list[str], market: Market) -> Priced[dict[str, list[str]]]:
        total, out = Decimal(0), {}
        for chunk in _chunks(keywords):
            task = await self.client.post(
                PATHS["intents"], {"keywords": chunk, "language_code": market.language_code}
            )
            total += task.cost
            out.update(n.intent_map(task.first.get("items")))
        return Priced(out, total)

    async def post_volume_task(self, keywords: list[str], market: Market) -> Priced[str]:
        if len(keywords) > MAX_BULK:
            raise ValueError(f"at most {MAX_BULK} keywords per volume task")
        task = await self.client.post(
            PATHS["volume_post"], {"keywords": keywords, **self._geo(market)}
        )
        return Priced(task.task_id, task.cost)

    async def get_volume_task(self, task_id: str, market: Market) -> list[KeywordMetrics] | None:
        task = await self.client.get(f"{PATHS['volume_get']}/{task_id}")
        if not task.ready:
            return None
        now = self.now()
        return [n.ads_volume_item(i, market, now) for i in task.result if i.get("keyword")]


def _chunks(items: list[str], size: int = MAX_BULK) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]
