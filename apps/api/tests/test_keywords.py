"""Phase 1 API: keyword overview/SERP/ideas, metering, truncation, lists, export, admin.

Runs on the fake provider (APP_ENV=test never builds the DataForSEO adapter).
"""

import csv
import io
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from seomaster_api.routers.keywords import csv_rows
from seomaster_api.services.keyword_filters import IdeaFilters, apply
from seomaster_core.markets import Market
from seomaster_core.seo import KeywordMetrics
from seomaster_db.models import Org, OrgMember, Plan, User
from seomaster_db.seed import PLANS
from seomaster_providers.fake import FakeKeywordProvider

SignUp = Callable[..., Awaitable[dict[str, str]]]
FREE: dict[str, int] = next(p for p in PLANS if p["id"] == "free")["limits"]


def unique(prefix: str = "seo tools") -> str:
    return f"{prefix} {time.time_ns() % 10**12}"


def email() -> str:
    return f"kw-{uuid.uuid4().hex[:10]}@example.com"


async def set_plan(app: FastAPI, user_email: str, **overrides: int) -> None:
    """Gives this user's org its own plan (copy of free + overrides)."""
    async with app.state.sessionmaker() as db:
        plan_id = f"t{uuid.uuid4().hex[:10]}"
        db.add(Plan(id=plan_id, name="Test", limits={**FREE, **overrides}))
        await db.flush()
        org = await db.scalar(
            select(Org)
            .join(OrgMember, OrgMember.org_id == Org.id)
            .join(User, User.id == OrgMember.user_id)
            .where(User.email == user_email)
        )
        assert org is not None
        org.plan_id = plan_id
        await db.commit()


async def usage(client: AsyncClient, name: str) -> int:
    data = (await client.get("/api/v1/limits/me")).json()["data"]
    return int(next(x for x in data["limits"] if x["name"] == name)["used"])


async def ideas(client: AsyncClient, seed: str, **params: Any) -> Any:
    r = await client.get("/api/v1/keywords/ideas", params={"seed": seed, "market": "us", **params})
    assert r.status_code == 200, r.text
    return r.json()


# -- overview + SERP --------------------------------------------------------------------------


async def test_overview_cache_ledger_and_single_report_charge(
    client: AsyncClient, sign_up: SignUp
) -> None:
    await sign_up(client)
    q = unique()
    first = await client.get("/api/v1/keywords/overview", params={"q": f"  {q.upper()} "})
    second = await client.get("/api/v1/keywords/overview", params={"q": q, "market": "in"})
    assert first.status_code == 200, first.text
    assert first.json()["data"]["keyword"] == q  # normalized
    assert first.json()["meta"]["cached"] is False
    assert first.json()["meta"]["source"] == "fake"
    assert second.json()["meta"]["cached"] is True
    assert first.json()["data"] == second.json()["data"]
    assert "provider;dur=" in first.headers["server-timing"]

    serp = await client.get("/api/v1/keywords/serp", params={"q": q, "market": "in"})
    assert serp.status_code == 200
    assert len(serp.json()["data"]["items"]) == 10
    # overview x2 + SERP of the same keyword = one report
    assert await usage(client, "reports_per_day") == 1

    admin = (await client.get("/api/v1/admin/usage")).json()["data"]
    tiers = {(r["cache_key"], r["cache_tier"]) for r in admin["recent"]}
    assert (f"kw:fake:in:{q}", "provider") in tiers
    assert (f"kw:fake:in:{q}", "hot") in tiers
    overview_row = next(e for e in admin["by_endpoint"] if e["endpoint"] == "keyword.overview")
    assert overview_row["views"] >= 2 and 0 < overview_row["hit_rate"] < 1
    assert admin["cost_per_view_usd"] > 0


async def test_invalid_keyword_rejected(client: AsyncClient, sign_up: SignUp) -> None:
    await sign_up(client)
    r = await client.get("/api/v1/keywords/overview", params={"q": "   "})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_keyword"


async def test_daily_report_limit_enforced(client: AsyncClient, sign_up: SignUp) -> None:
    await sign_up(client)
    base = unique("limit")
    for i in range(FREE["reports_per_day"]):
        r = await client.get("/api/v1/keywords/overview", params={"q": f"{base} {i}"})
        assert r.status_code == 200
    again = await client.get("/api/v1/keywords/overview", params={"q": f"{base} 0"})
    assert again.status_code == 200  # an already-opened report stays free
    blocked = await client.get("/api/v1/keywords/overview", params={"q": f"{base} new"})
    assert blocked.status_code == 429
    assert blocked.json()["error"]["details"]["metric"] == "reports_per_day"


async def test_requires_auth(client: AsyncClient) -> None:
    client.cookies.clear()
    r = await client.get("/api/v1/keywords/overview", params={"q": "seo"})
    assert r.status_code == 401


# -- ideas (Keyword Magic) ------------------------------------------------------------------


async def test_ideas_sort_pagination_and_filters(
    app: FastAPI, client: AsyncClient, sign_up: SignUp
) -> None:
    addr = email()
    await sign_up(client, addr)
    await set_plan(app, addr, ideas_rows_per_report=500, keyword_ideas_rows=10_000)
    seed = unique("crm")

    full = await ideas(client, seed, limit=100)
    rows = full["data"]
    total = full["meta"]["page"]["total"]
    assert total == len(rows) > 20 and full["meta"]["limited"] is False
    vols = [r["volume"] for r in rows]
    assert vols == sorted(vols, reverse=True)

    p1 = (await ideas(client, seed, offset=0, limit=10))["data"]
    p2 = (await ideas(client, seed, offset=10, limit=10))["data"]
    assert [r["keyword"] for r in p1 + p2] == [r["keyword"] for r in rows[:20]]

    by_kd = (await ideas(client, seed, sort="kd", dir="asc", limit=100))["data"]
    kds = [r["kd"] for r in by_kd]
    assert kds == sorted(kds)

    filt = await ideas(client, seed, kd_max=50, include="best", limit=100)
    assert all(r["kd"] <= 50 and "best" in r["keyword"] for r in filt["data"])
    assert filt["meta"]["page"]["total"] == len(filt["data"])

    # same seed + mode in every call above -> one report
    assert await usage(client, "reports_per_day") == 1


def test_filters_unknown_values_fail_bounds_and_sort_last() -> None:
    fake = FakeKeywordProvider()
    rows = [fake.metrics(k, Market.US) for k in ["a b", "a b c", "x y z w", "best a"]]
    rows.append(rows[0].model_copy(update={"keyword": "unknown kd", "kd": None}))
    kept = apply(rows, IdeaFilters(words_min=2, words_max=3, exclude=["best"]), "kd", "asc")
    assert {m.keyword for m in kept} == {"a b", "a b c", "unknown kd"}
    assert kept[-1].keyword == "unknown kd"  # None sorts last
    assert "unknown kd" not in {m.keyword for m in apply(rows, IdeaFilters(kd_max=100))}


async def test_plan_truncation_and_row_metering(
    app: FastAPI, client: AsyncClient, sign_up: SignUp
) -> None:
    addr = email()
    await sign_up(client, addr)
    await set_plan(app, addr, ideas_rows_per_report=15, keyword_ideas_rows=20)
    alpha, beta = unique("alpha"), unique("beta")

    a = await ideas(client, alpha, limit=50)
    assert len(a["data"]) == 15 and a["meta"]["limited"] is True
    assert a["meta"]["page"]["total"] > 15

    beyond = await ideas(client, alpha, offset=15, limit=10)
    assert beyond["data"] == [] and beyond["meta"]["limited"] is True

    again = await ideas(client, alpha, limit=50)
    assert len(again["data"]) == 15  # rows already seen today are not re-charged

    b = await ideas(client, beta, limit=50)
    assert len(b["data"]) == 5 and b["meta"]["limited"] is True  # 20 - 15 rows left today
    assert await usage(client, "keyword_ideas_rows") == 20


# -- export ------------------------------------------------------------------------------------


async def test_export_blocked_on_free_plan(client: AsyncClient, sign_up: SignUp) -> None:
    await sign_up(client)
    r = await client.get("/api/v1/keywords/ideas/export.csv", params={"seed": "seo"})
    assert r.status_code == 429
    assert r.json()["error"]["details"]["metric"] == "exports_per_day"


async def test_export_csv(app: FastAPI, client: AsyncClient, sign_up: SignUp) -> None:
    addr = email()
    await sign_up(client, addr)
    await set_plan(app, addr, exports_per_day=5, ideas_rows_per_report=500)
    r = await client.get(
        "/api/v1/keywords/ideas/export.csv", params={"seed": "Seo Tools", "market": "us"}
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert 'filename="brandiz-ideas-us-seo-tools.csv"' in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text)))
    assert rows[0] == ["keyword", "volume", "kd", "cpc", "competition", "intents", "serp_features"]
    assert len(rows) > 10
    assert await usage(client, "exports_per_day") == 1


def test_csv_cells_neutralize_formulas() -> None:
    m = KeywordMetrics(
        keyword="=hyperlink(1)", market=Market.US, source="t", fetched_at=datetime.now(UTC)
    )
    assert "'=hyperlink(1)" in csv_rows([m])


# -- lists ---------------------------------------------------------------------------------------


async def test_lists_crud_items_and_limits(client: AsyncClient, sign_up: SignUp) -> None:
    headers = await sign_up(client)
    known = unique("known")
    await client.get("/api/v1/keywords/overview", params={"q": known, "market": "us"})

    r = await client.post(
        "/api/v1/keywords/lists", json={"name": "Launch", "market": "us"}, headers=headers
    )
    assert r.status_code == 201, r.text
    list_id = r.json()["data"]["id"]

    second = await client.post("/api/v1/keywords/lists", json={"name": "Two"}, headers=headers)
    assert second.status_code == 429  # free plan: 1 list
    assert second.json()["error"]["details"]["metric"] == "keyword_lists"

    never_seen = unique("brand new")
    add = await client.post(
        f"/api/v1/keywords/lists/{list_id}/items",
        json={"keywords": [known.upper(), never_seen, known, "  "]},
        headers=headers,
    )
    assert add.status_code == 200, add.text
    assert add.json()["data"] == {"added": 2, "total": 2}

    again = await client.post(
        f"/api/v1/keywords/lists/{list_id}/items", json={"keywords": [known]}, headers=headers
    )
    assert again.json()["data"] == {"added": 0, "total": 2}

    detail = (await client.get(f"/api/v1/keywords/lists/{list_id}")).json()["data"]
    assert detail["info"]["item_count"] == 2
    items = {i["keyword"]: i for i in detail["items"]}
    assert items[known]["volume"] is not None  # copied from keyword_metrics
    assert items[known]["metrics_updated_at"] is not None
    assert items[never_seen]["volume"] is None  # filled later by the volume job

    lists = (await client.get("/api/v1/keywords/lists")).json()["data"]
    assert [(x["name"], x["item_count"]) for x in lists] == [("Launch", 2)]

    item_id = items[never_seen]["id"]
    rm = await client.delete(f"/api/v1/keywords/lists/{list_id}/items/{item_id}", headers=headers)
    assert rm.status_code == 204

    blocked = await client.get(f"/api/v1/keywords/lists/{list_id}/export.csv")
    assert blocked.status_code == 429  # free: no exports

    gone = await client.delete(f"/api/v1/keywords/lists/{list_id}", headers=headers)
    assert gone.status_code == 204
    assert (await client.get(f"/api/v1/keywords/lists/{list_id}")).status_code == 404


async def test_list_org_isolation(sign_up: SignUp, new_client: Callable[[], AsyncClient]) -> None:
    async with new_client() as alice, new_client() as bob:
        a = await sign_up(alice)
        b = await sign_up(bob)
        r = await alice.post("/api/v1/keywords/lists", json={"name": "Mine"}, headers=a)
        list_id = r.json()["data"]["id"]
        assert (await bob.get(f"/api/v1/keywords/lists/{list_id}")).status_code == 404
        steal = await bob.post(
            f"/api/v1/keywords/lists/{list_id}/items", json={"keywords": ["x"]}, headers=b
        )
        assert steal.status_code == 404
        assert (await bob.delete(f"/api/v1/keywords/lists/{list_id}", headers=b)).status_code == 404
