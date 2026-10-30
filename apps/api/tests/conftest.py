"""API integration tests: real Postgres/Redis/ClickHouse from infra/docker-compose.dev.yml.

Isolated from dev data: Postgres `seomaster_test`, Redis db 15, ClickHouse `seomaster_test`.
"""

import os

os.environ.update(
    APP_ENV="test",
    DATABASE_URL="postgresql+asyncpg://seomaster:seomaster@localhost:5432/seomaster_test",
    REDIS_URL="redis://localhost:6379/15",
    CELERY_BROKER_URL="redis://localhost:6379/14",
    CLICKHOUSE_DATABASE="seomaster_test",
    SIGNUP_RATE_LIMIT_PER_MIN="1000",  # many signups from one test IP
)

import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import insert

from seomaster_core.config import get_settings
from seomaster_db.base import Base, make_engine
from seomaster_db.clickhouse import migrate
from seomaster_db.models import Plan
from seomaster_db.seed import PLANS

get_settings.cache_clear()

PASSWORD = "correct horse battery"
SignUp = Callable[..., Awaitable[dict[str, str]]]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "apps/api/tests" in str(item.path):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
async def app() -> AsyncIterator[FastAPI]:
    from seomaster_api.app import create_app

    settings = get_settings()
    engine = make_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(insert(Plan), PLANS)
    await engine.dispose()

    await migrate(settings)
    redis = Redis.from_url(settings.redis_url)
    await redis.flushdb()
    await redis.aclose()

    from seomaster_api.mailer import MemoryMailer

    application = create_app(settings)
    application.state.mailer = MemoryMailer()
    async with application.router.lifespan_context(application):
        yield application


def make_client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://api.seomaster.test")


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with make_client(app) as c:
        yield c


async def signup_token(client: AsyncClient, email: str) -> str:
    """Signs up and returns the token from the verification email (captured by MemoryMailer)."""
    r = await client.post(
        "/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "name": "Test"}
    )
    assert r.status_code == 201, r.text
    return last_token(client, email)


def last_token(client: AsyncClient, email: str) -> str:
    app = client._transport.app  # type: ignore[attr-defined]
    sent = [m for m in app.state.mailer.outbox if m.to == email.lower()]
    assert sent, f"no email sent to {email}"
    url = re.search(r"https?://\S+/verify\?token=\S+", sent[-1].text)
    assert url, "verification link missing from email"
    return parse_qs(urlsplit(url.group(0)).query)["token"][0]


async def _sign_up_and_verify(client: AsyncClient, email: str | None = None) -> dict[str, str]:
    token = await signup_token(client, email or f"user-{uuid.uuid4().hex[:8]}@example.com")
    r = await client.post("/api/v1/auth/verify", json={"token": token})
    assert r.status_code == 200, r.text
    return {"x-csrf-token": client.cookies["sm_csrf"]}


@pytest.fixture
def sign_up() -> SignUp:
    """`headers = await sign_up(client)` -> verified, signed-in user + CSRF header."""
    return _sign_up_and_verify


@pytest.fixture
def get_token() -> Callable[[AsyncClient, str], Awaitable[str]]:
    return signup_token


@pytest.fixture
def new_client(app: FastAPI) -> Callable[[], AsyncClient]:
    return lambda: make_client(app)


@pytest.fixture
def outbox(app: FastAPI) -> list:  # type: ignore[type-arg]
    return app.state.mailer.outbox  # type: ignore[no-any-return]
