"""DataForSEO adapter on recorded-style fixtures only: never touches the live API."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from seomaster_core.markets import Market
from seomaster_providers.dataforseo import normalize as n
from seomaster_providers.dataforseo.adapter import PATHS, DataForSEOKeywordProvider
from seomaster_providers.dataforseo.client import (
    DataForSEOAuthError,
    DataForSEOClient,
    DataForSEOPaymentError,
    DataForSEORateLimitError,
    DataForSEORequestError,
    DataForSEOServerError,
)

FIXTURES = Path(__file__).parent / "fixtures" / "dataforseo"
NOW = datetime(2026, 10, 30, 8, 0, tzinfo=UTC)
Routes = dict[str, list[tuple[int, Any]]]


def fx(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())  # type: ignore[no-any-return]


class Router:
    """MockTransport handler: path prefix -> queue of (status, body); the last entry repeats."""

    def __init__(self, routes: Routes) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/v3/")
        for prefix, queue in self.routes.items():
            if path.startswith(prefix):
                status, body = queue.pop(0) if len(queue) > 1 else queue[0]
                if isinstance(body, Exception):
                    raise body
                return httpx.Response(status, json=body)
        return httpx.Response(404, json={"status_code": 40400, "status_message": "Not Found."})

    def body(self, i: int = -1) -> dict[str, Any]:
        return json.loads(self.requests[i].content)[0]  # type: ignore[no-any-return]


def provider(routes: Routes) -> tuple[DataForSEOKeywordProvider, Router]:
    router = Router(routes)
    client = DataForSEOClient(
        "login@example.com", "secret", transport=httpx.MockTransport(router), backoff_s=0
    )
    return DataForSEOKeywordProvider(client, now=lambda: NOW), router


# -- normalizers ---------------------------------------------------------------------------------


async def test_overview_normalizes_snapshot() -> None:
    p, router = provider({PATHS["overview"]: [(200, fx("keyword_overview.json"))]})
    priced = await p.overview("seo tools", Market.US)
    m = priced.value
    assert priced.cost_usd == Decimal("0.0101")
    assert m.model_dump(exclude={"trend", "trend_months"}) == {
        "keyword": "seo tools",
        "market": Market.US,
        "volume": 49500,
        "cpc": 9.12,
        "competition": 0.31,
        "kd": 82,
        "intents": ["commercial", "informational"],
        "serp_features": ["people_also_ask", "related_searches"],
        "source": "dataforseo_labs",
        "fetched_at": NOW,
    }
    # oldest -> newest, 12 months, labels aligned with values
    assert m.trend_months[0] == "2024-11" and m.trend_months[-1] == "2025-10"
    assert m.trend[-1] == 49500 and len(m.trend) == 12

    sent = router.body()
    assert sent["keywords"] == ["seo tools"]
    assert sent["location_code"] == 2840 and sent["language_code"] == "en"
    assert router.requests[0].headers["authorization"].startswith("Basic ")


async def test_overview_no_data_is_none_not_zero() -> None:
    p, _ = provider({PATHS["overview"]: [(200, fx("keyword_overview_empty.json"))]})
    m = (await p.overview("zzqx nonsense", Market.IN)).value
    assert m.keyword == "zzqx nonsense"
    assert (m.volume, m.kd, m.cpc, m.competition) == (None, None, None, None)
    assert not m.has_data


async def test_ideas_normalize_dedupe_and_unknowns() -> None:
    p, router = provider({PATHS["ideas"]: [(200, fx("keyword_ideas.json"))]})
    priced = await p.ideas("seo tools", Market.IN, "ideas", 500)
    rows = {m.keyword: m for m in priced.value}
    assert list(rows) == [
        "seo tools",
        "free seo tools",  # lowercased
        "seo tools for agencies",  # whitespace collapsed
        "best seo tools",
        "seo checker",
    ]
    unknown = rows["seo checker"]
    assert unknown.volume is None and unknown.kd is None and unknown.trend == []
    assert rows["free seo tools"].intents == ["transactional", "informational"]
    assert all(m.market == Market.IN for m in priced.value)
    assert router.body()["limit"] == 500
    assert router.body()["location_code"] == 2356


async def test_related_unwraps_keyword_data() -> None:
    p, router = provider({PATHS["related"]: [(200, fx("related_keywords.json"))]})
    rows = (await p.ideas("seo tools", Market.US, "related", 100)).value
    assert [m.keyword for m in rows] == ["seo tools", "free seo tools", "seo tools for agencies"]
    assert router.body()["keyword"] == "seo tools" and router.body()["depth"] == 2


async def test_suggestions_endpoint() -> None:
    p, router = provider({PATHS["suggestions"]: [(200, fx("keyword_suggestions.json"))]})
    rows = (await p.ideas("seo tools", Market.US, "suggestions", 100)).value
    assert len(rows) == 3
    assert "keyword_suggestions" in router.requests[0].url.path


async def test_serp_top10_sorted_and_features() -> None:
    p, router = provider({PATHS["serp"]: [(200, fx("serp_organic.json"))]})
    snap = (await p.serp("seo tools", Market.US)).value
    assert [i.position for i in snap.items] == list(range(1, 11))
    assert snap.items[0].url == "https://www.site1.com/seo-tools"
    assert snap.items[0].title == "Result 1"
    assert snap.features == ["people_also_ask", "related_searches", "video"]
    assert router.body()["depth"] == 10


async def test_difficulty_and_intents_maps() -> None:
    p, _ = provider(
        {
            PATHS["difficulty"]: [(200, fx("bulk_keyword_difficulty.json"))],
            PATHS["intents"]: [(200, fx("search_intent.json"))],
        }
    )
    kd = await p.difficulty(["seo tools", "rank tracker", "obscure phrase"], Market.US)
    assert kd.value == {"seo tools": 82, "rank tracker": 64, "obscure phrase": None}
    intents = await p.intents(["seo tools", "buy seo software"], Market.US)
    assert intents.value == {
        "seo tools": ["commercial", "informational"],
        "buy seo software": ["transactional"],
    }
    assert intents.cost_usd == Decimal("0.0012")


async def test_volume_task_post_and_get() -> None:
    p, router = provider(
        {
            PATHS["volume_post"]: [(200, fx("volume_task_post.json"))],
            PATHS["volume_get"]: [
                (200, fx("volume_task_get_queued.json")),
                (200, fx("volume_task_get.json")),
            ],
        }
    )
    posted = await p.post_volume_task(["seo tools", "rare phrase"], Market.IN)
    assert posted.value == "11011200-1535-0110-0000-1a2b3c4d5e6f"
    assert posted.cost_usd == Decimal("0.05")

    assert await p.get_volume_task(posted.value, Market.IN) is None  # still queued
    rows = await p.get_volume_task(posted.value, Market.IN)
    assert rows is not None
    by_kw = {m.keyword: m for m in rows}
    assert by_kw["seo tools"].volume == 14800
    assert by_kw["seo tools"].competition == 0.87
    assert by_kw["seo tools"].source == "google_ads"
    assert by_kw["rare phrase"].volume is None
    assert router.requests[-1].url.path.endswith(posted.value)


async def test_volume_task_rejects_oversized_batch() -> None:
    p, _ = provider({})
    with pytest.raises(ValueError, match="at most 1000"):
        await p.post_volume_task([f"k{i}" for i in range(1001)], Market.IN)


def test_trend_handles_missing_months() -> None:
    values, months = n.trend(
        [{"year": 2026, "month": 2, "search_volume": None}, {"year": 2026, "month": 1}]
    )
    assert months == ["2026-01", "2026-02"] and values == [None, None]
    assert n.trend(None) == ([], [])


# -- client: errors, retries, cost ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "fixture", "error"),
    [
        (401, "error_auth.json", DataForSEOAuthError),
        (200, "error_balance.json", DataForSEOPaymentError),
        (200, "error_invalid_field.json", DataForSEORequestError),
    ],
)
async def test_error_codes_mapped_and_not_retried(
    status: int, fixture: str, error: type[Exception]
) -> None:
    p, router = provider({PATHS["overview"]: [(status, fx(fixture))]})
    with pytest.raises(error):
        await p.overview("seo tools", Market.US)
    assert len(router.requests) == 1  # client errors are never retried


async def test_server_errors_retried_then_succeed() -> None:
    p, router = provider(
        {
            PATHS["overview"]: [
                (502, {"status_code": 50200}),
                (200, fx("error_internal.json")),
                (200, fx("keyword_overview.json")),
            ]
        }
    )
    m = (await p.overview("seo tools", Market.US)).value
    assert m.volume == 49500
    assert len(router.requests) == 3


async def test_retries_are_bounded() -> None:
    p, router = provider({PATHS["overview"]: [(503, {"status_code": 50300})]})
    with pytest.raises(DataForSEOServerError):
        await p.overview("seo tools", Market.US)
    assert len(router.requests) == 3  # max_attempts


async def test_rate_limit_retried_then_raised() -> None:
    p, router = provider({PATHS["overview"]: [(429, {"status_code": 40202})]})
    with pytest.raises(DataForSEORateLimitError):
        await p.overview("seo tools", Market.US)
    assert len(router.requests) == 3


async def test_network_error_retried() -> None:
    p, router = provider(
        {
            PATHS["overview"]: [
                (0, httpx.ConnectError("boom")),
                (200, fx("keyword_overview.json")),
            ]
        }
    )
    assert (await p.overview("seo tools", Market.US)).value.kd == 82
    assert len(router.requests) == 2
