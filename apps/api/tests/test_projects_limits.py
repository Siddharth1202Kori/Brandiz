import asyncio
from collections.abc import Awaitable, Callable

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from seomaster_api.errors import QuotaExceededError
from seomaster_api.services import limits
from seomaster_db.models import Org, OrgMember, User

SignUp = Callable[..., Awaitable[dict[str, str]]]


async def test_create_project_normalizes_domain(client: AsyncClient, sign_up: SignUp) -> None:
    headers = await sign_up(client)
    r = await client.post(
        "/api/v1/projects",
        json={"name": "Shop", "domain": "HTTPS://WWW.Shop-Example.co.in/path", "market": "in"},
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["data"]["domain"] == "shop-example.co.in"


async def test_invalid_domain_rejected(client: AsyncClient, sign_up: SignUp) -> None:
    headers = await sign_up(client)
    r = await client.post(
        "/api/v1/projects", json={"name": "Bad", "domain": "localhost"}, headers=headers
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_domain"


async def test_free_plan_project_limit(client: AsyncClient, sign_up: SignUp) -> None:
    headers = await sign_up(client)
    first = {"name": "One", "domain": "one-example.com"}
    assert (await client.post("/api/v1/projects", json=first, headers=headers)).status_code == 201
    r = await client.post(
        "/api/v1/projects", json={"name": "Two", "domain": "two-example.com"}, headers=headers
    )
    assert r.status_code == 429
    assert r.json()["error"]["details"] == {"metric": "projects", "limit": 1}

    data = (await client.get("/api/v1/limits/me")).json()["data"]
    projects = next(x for x in data["limits"] if x["name"] == "projects")
    assert projects == {"name": "projects", "used": 1, "max": 1, "period": "total"}


async def test_org_isolation(sign_up: SignUp, new_client: Callable[[], AsyncClient]) -> None:
    async with new_client() as alice, new_client() as bob:
        a_headers = await sign_up(alice)
        b_headers = await sign_up(bob)
        r = await alice.post(
            "/api/v1/projects", json={"name": "A", "domain": "alice-site.com"}, headers=a_headers
        )
        project_id = r.json()["data"]["id"]

        assert (await bob.get(f"/api/v1/projects/{project_id}")).status_code == 404
        r = await bob.delete(f"/api/v1/projects/{project_id}", headers=b_headers)
        assert r.status_code == 404
        assert (await bob.get("/api/v1/projects")).json()["data"] == []
        assert (await alice.get(f"/api/v1/projects/{project_id}")).status_code == 200


async def test_concurrent_consume_never_exceeds_limit(
    client: AsyncClient, app: FastAPI, sign_up: SignUp
) -> None:
    await sign_up(client)
    me = (await client.get("/api/v1/auth/me")).json()["data"]
    sessionmaker = app.state.sessionmaker
    async with sessionmaker() as db:
        org = await db.get(Org, me["org"]["id"])
    assert org is not None

    async def one() -> bool:
        async with sessionmaker() as db:
            try:
                await limits.consume(db, org, "reports_per_day")
                await db.commit()
                return True
            except QuotaExceededError:
                return False

    results = await asyncio.gather(*(one() for _ in range(25)))
    assert sum(results) == 10  # free plan reports_per_day


async def test_healthz(client: AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    checks = r.json()["checks"]
    assert checks["postgres"]["ok"] and checks["redis"]["ok"] and checks["clickhouse"]["ok"]


async def test_google_user_upsert_links_by_email(app: FastAPI) -> None:
    from seomaster_api.routers.auth import _upsert_google_user

    info = {"sub": "g-123", "email": "Linked@Example.com", "email_verified": True, "name": "L"}
    async with app.state.sessionmaker() as db:
        created = await _upsert_google_user(db, info)
        await db.commit()
        again = await _upsert_google_user(db, info)
        assert again.id == created.id
        member = await db.scalar(select(OrgMember).where(OrgMember.user_id == created.id))
        assert member is not None and member.role == "owner"
        user = await db.get(User, created.id)
        assert user is not None and user.email == "linked@example.com" and user.email_verified
