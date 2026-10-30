"""FastAPI dependencies: DB session, current user/org, quota."""

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from seomaster_api.errors import AppError
from seomaster_api.mailer import Mailer
from seomaster_api.security import SESSION_COOKIE, read_session
from seomaster_api.services import limits
from seomaster_core.config import Settings, get_settings
from seomaster_db.models import Org, OrgMember, User
from seomaster_providers.dal import DataAccessLayer
from seomaster_providers.keywords import KeywordService


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session


def get_redis(request: Request) -> Redis:
    return request.app.state.redis  # type: ignore[no-any-return]


def get_dal(request: Request) -> DataAccessLayer:
    return request.app.state.dal  # type: ignore[no-any-return]


def get_keywords(request: Request) -> KeywordService:
    return request.app.state.keywords  # type: ignore[no-any-return]


def get_mailer(request: Request) -> Mailer:
    return request.app.state.mailer  # type: ignore[no-any-return]


DB = Annotated[AsyncSession, Depends(get_db)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]
RedisDep = Annotated[Redis, Depends(get_redis)]
DAL = Annotated[DataAccessLayer, Depends(get_dal)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
Keywords = Annotated[KeywordService, Depends(get_keywords)]


async def current_user(request: Request, db: DB, settings: SettingsDep) -> User:
    user_id = read_session(request.cookies.get(SESSION_COOKIE), settings)
    user = await db.get(User, user_id) if user_id else None
    if user is None:
        raise AppError(401, "unauthenticated", "Sign in required")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def current_org(user: CurrentUser, db: DB) -> Org:
    """Phase 0: every user has exactly one (personal) org. Org switching comes with teams."""
    org = await db.scalar(
        select(Org)
        .join(OrgMember, OrgMember.org_id == Org.id)
        .where(OrgMember.user_id == user.id)
        .order_by(Org.created_at)
        .limit(1)
    )
    if org is None:
        raise AppError(403, "no_org", "No workspace for this user")
    return org


CurrentOrg = Annotated[Org, Depends(current_org)]


def require_quota(metric: str, amount: int = 1) -> Callable[..., Awaitable[None]]:
    """Consumes `amount` of a metered metric before the endpoint runs (commits immediately)."""

    async def _dep(org: CurrentOrg, db: DB) -> None:
        await limits.consume(db, org, metric, amount)
        await db.commit()

    return _dep


async def require_admin(user: CurrentUser, settings: SettingsDep) -> User:
    """ADMIN_EMAILS (comma separated) gates admin pages; empty = everyone, outside prod."""
    allowed = {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}
    if (allowed and user.email.lower() not in allowed) or (not allowed and settings.is_prod):
        raise AppError(403, "forbidden", "Admins only")
    return user
