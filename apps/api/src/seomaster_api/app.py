"""FastAPI app factory. Run: `uvicorn seomaster_api.app:create_app --factory`."""

import logging
import secrets
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from starlette.middleware.sessions import SessionMiddleware

from seomaster_api import errors
from seomaster_api.mailer import SmtpMailer
from seomaster_api.routers import admin, auth, health, keywords, limits, lists, projects
from seomaster_api.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from seomaster_core import timing
from seomaster_core.config import Settings, get_settings
from seomaster_core.observability import request_id_var, setup_logging, setup_tracing
from seomaster_db.base import make_engine, make_sessionmaker
from seomaster_db.clickhouse import ClickHouseHandle
from seomaster_providers.factory import (
    build_keyword_provider,
    build_keyword_service,
    close_provider,
)

log = logging.getLogger(__name__)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT = {
    "/api/v1/auth/login",
    "/api/v1/auth/signup",
    "/api/v1/auth/verify",
    "/api/v1/auth/resend-verification",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    s: Settings = app.state.settings
    engine = make_engine(s.database_url)
    redis: Redis = Redis.from_url(s.redis_url, decode_responses=True)
    clickhouse = ClickHouseHandle(s)
    app.state.engine = engine
    app.state.sessionmaker = make_sessionmaker(engine)
    app.state.redis = redis
    app.state.clickhouse = clickhouse
    provider = build_keyword_provider(s)
    app.state.keywords = build_keyword_service(s, redis, clickhouse, provider)
    app.state.dal = app.state.keywords.dal
    log.info("keyword provider: %s", provider.name)
    try:
        yield
    finally:
        await close_provider(provider)
        await clickhouse.close()
        await redis.aclose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or get_settings()
    setup_logging(json_logs=s.app_env != "dev")
    if s.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(
            dsn=s.sentry_dsn, environment=s.app_env, traces_sample_rate=0.1, send_default_pii=False
        )

    app = FastAPI(
        title="Brandiz API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if s.is_prod else "/docs",
        redoc_url=None,
    )
    app.state.settings = s
    app.state.oauth = auth.build_oauth(s)
    app.state.mailer = SmtpMailer(s)  # tests swap in MemoryMailer
    errors.install(app)

    @app.middleware("http")
    async def csrf_guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if (
            request.method not in SAFE_METHODS
            and request.cookies.get(SESSION_COOKIE)
            and request.url.path not in CSRF_EXEMPT
        ):
            cookie = request.cookies.get(CSRF_COOKIE, "")
            header = request.headers.get(CSRF_HEADER, "")
            if not cookie or not secrets.compare_digest(cookie, header):
                return errors.error_response(403, "csrf_failed", "Missing or invalid CSRF token")
        return await call_next(request)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request_id_var.set(rid)
        timing.start()
        t0 = time.perf_counter()
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        response.headers["x-service"] = "api"
        response.headers["server-timing"] = timing.header_value((time.perf_counter() - t0) * 1000)
        return response

    # Starlette runs the last-added middleware first: CORS -> session -> context -> csrf.
    app.add_middleware(
        SessionMiddleware,  # only holds OAuth state during the Google redirect
        secret_key=s.auth_secret.get_secret_value(),
        session_cookie="sm_oauth",
        max_age=600,
        same_site="lax",
        https_only=s.is_prod,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[s.web_base_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["server-timing", "x-request-id"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(projects.router)
    app.include_router(limits.router)
    app.include_router(keywords.router)
    app.include_router(lists.router)
    app.include_router(admin.router)

    if setup_tracing("seomaster-api", s.otel_exporter_otlp_endpoint):
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    return app
