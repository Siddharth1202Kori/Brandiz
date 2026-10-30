"""Deterministic fake provider: lets UI and tests run without spending provider credit.

Same keyword + market always yields the same numbers. Costs are tiny but non-zero so the
ledger and budget guard behave like they do with a real provider.
"""

import hashlib
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import ClassVar

from seomaster_core.markets import Market
from seomaster_core.seo import KeywordMetrics, SerpItem, SerpSnapshot
from seomaster_providers.interfaces import IdeasMode, Priced

FAKE_COST = Decimal("0.0001")
INTENTS = ["informational", "commercial", "transactional", "navigational"]
MODIFIERS = {
    "ideas": [
        "best",
        "free",
        "online",
        "tool",
        "software",
        "app",
        "price",
        "review",
        "top",
        "cheap",
    ],
    "related": ["alternative", "vs", "like", "for beginners", "guide", "tips", "examples"],
    "suggestions": ["near me", "how to", "what is", "for small business", "2026", "india", "list"],
}


def _seed(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:8], 16)


class FakeKeywordProvider:
    name = "fake"
    # Process-wide: Celery builds a new provider per task, but post + collect share a worker.
    _tasks: ClassVar[dict[str, tuple[list[str], Market]]] = {}

    def __init__(self) -> None:
        self.calls = 0

    def metrics(self, kw: str, market: Market) -> KeywordMetrics:
        s = _seed(kw, market)
        months = [f"{2025 + (m + 10) // 12:04d}-{(m + 10) % 12 + 1:02d}" for m in range(12)]
        volume = (s % 50_000) + 10
        return KeywordMetrics(
            keyword=kw,
            market=market,
            volume=volume,
            cpc=round((s % 500) / 100, 2),
            competition=round((s % 100) / 100, 2),
            kd=s % 101,
            intents=[INTENTS[s % 4]],
            trend=[max(0, volume + ((s >> i) % 41 - 20) * volume // 100) for i in range(12)],
            trend_months=months,
            serp_features=["people_also_ask", "related_searches"][: s % 3],
            source=self.name,
            fetched_at=datetime.now(UTC),
        )

    async def overview(self, kw: str, market: Market) -> Priced[KeywordMetrics]:
        self.calls += 1
        return Priced(self.metrics(kw, market), FAKE_COST)

    async def ideas(
        self, seed: str, market: Market, mode: IdeasMode, limit: int
    ) -> Priced[list[KeywordMetrics]]:
        self.calls += 1
        words = MODIFIERS[mode]
        phrases = [f"{seed} {w}" for w in words] + [f"{w} {seed}" for w in words]
        phrases += [f"{a} {seed} {b}" for a in words[:5] for b in words[5:]]
        items = sorted(
            (self.metrics(p, market) for p in phrases[:limit]),
            key=lambda m: m.volume or 0,
            reverse=True,
        )
        return Priced(items, FAKE_COST * len(items))

    async def serp(self, kw: str, market: Market) -> Priced[SerpSnapshot]:
        self.calls += 1
        slug = kw.replace(" ", "-")
        items = [
            SerpItem(
                position=i,
                url=f"https://site{i}.example.com/{slug}",
                domain=f"site{i}.example.com",
                title=f"{kw.title()} — result {i}",
            )
            for i in range(1, 11)
        ]
        snap = SerpSnapshot(
            keyword=kw,
            market=market,
            items=items,
            features=["people_also_ask"],
            taken_at=datetime.now(UTC),
        )
        return Priced(snap, FAKE_COST)

    async def difficulty(
        self, keywords: list[str], market: Market
    ) -> Priced[dict[str, int | None]]:
        self.calls += 1
        return Priced({k: self.metrics(k, market).kd for k in keywords}, FAKE_COST)

    async def intents(self, keywords: list[str], market: Market) -> Priced[dict[str, list[str]]]:
        self.calls += 1
        return Priced({k: self.metrics(k, market).intents for k in keywords}, FAKE_COST)

    async def post_volume_task(self, keywords: list[str], market: Market) -> Priced[str]:
        self.calls += 1
        task_id = uuid.uuid4().hex
        self._tasks[task_id] = (keywords, market)
        return Priced(task_id, FAKE_COST)

    async def get_volume_task(self, task_id: str, market: Market) -> list[KeywordMetrics] | None:
        keywords, mkt = self._tasks.pop(task_id, ([], market))
        return [self.metrics(k, mkt) for k in keywords]
