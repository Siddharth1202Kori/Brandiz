"""/api/v1/auth — email+password with verification, Google OAuth, session cookies."""

import logging
import uuid
from typing import Annotated, Any

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from seomaster_api.deps import DB, CurrentOrg, CurrentUser, MailerDep, RedisDep, SettingsDep
from seomaster_api.errors import AppError
from seomaster_api.mailer import Mailer, verification_email
from seomaster_api.security import (
    clear_session,
    hash_password,
    issue_session,
    make_email_token,
    rate_limit,
    read_email_token,
    verify_password,
)
from seomaster_api.services.accounts import create_user_with_org
from seomaster_core.config import Settings
from seomaster_core.markets import Market
from seomaster_core.models import Envelope
from seomaster_db.models import Org, User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    name: str | None = Field(default=None, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=200)


class VerifyIn(BaseModel):
    token: str


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str
    plan_id: str


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    name: str | None
    email_verified: bool
    market: Market
    org: OrgOut


class MePatch(BaseModel):
    market: Market | None = None
    name: str | None = Field(default=None, max_length=200)


class SignupOut(BaseModel):
    email: str
    verification_required: bool = True


class ResendIn(BaseModel):
    email: EmailStr


class AcceptedOut(BaseModel):
    accepted: bool = True


def _me(user: User, org: Org) -> Envelope[MeOut]:
    return Envelope(
        data=MeOut(
            id=user.id,
            email=user.email,
            name=user.name,
            email_verified=user.email_verified,
            market=Market(user.market),
            org=OrgOut(id=org.id, name=org.name, plan_id=org.plan_id),
        )
    )


async def _org_for(db: DB, user: User) -> Org:
    from seomaster_api.deps import current_org

    return await current_org(user, db)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _send_verification(mailer: Mailer, settings: Settings, user: User) -> None:
    """The link is only ever delivered by email, never returned in an API response."""
    url = f"{settings.web_base_url}/verify?token={make_email_token(user.email, settings)}"
    try:
        await mailer.send(verification_email(user.email, user.name, url))
    except Exception:  # account exists; user can request a resend
        log.exception("verification email failed for user %s", user.id)


@router.post("/signup", status_code=201)
async def signup(
    body: SignupIn,
    request: Request,
    db: DB,
    redis: RedisDep,
    settings: SettingsDep,
    mailer: MailerDep,
) -> Envelope[SignupOut]:
    await rate_limit(
        redis, f"signup:{_client_ip(request)}", limit=settings.signup_rate_limit_per_min
    )
    email = body.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise AppError(409, "email_taken", "An account with this email already exists")
    user = await create_user_with_org(
        db, email=email, name=body.name, password_hash=hash_password(body.password)
    )
    await db.commit()
    await _send_verification(mailer, settings, user)
    return Envelope(data=SignupOut(email=email))


@router.post("/resend-verification", status_code=202)
async def resend_verification(
    body: ResendIn,
    request: Request,
    db: DB,
    redis: RedisDep,
    settings: SettingsDep,
    mailer: MailerDep,
) -> Envelope[AcceptedOut]:
    """Always 202 so the endpoint can't be used to discover which emails have accounts."""
    email = body.email.lower()
    await rate_limit(redis, f"resend:{_client_ip(request)}:{email}", limit=3, window_s=600)
    user = await db.scalar(select(User).where(User.email == email))
    if user is not None and not user.email_verified and user.password_hash:
        await _send_verification(mailer, settings, user)
    return Envelope(data=AcceptedOut())


@router.post("/verify")
async def verify(
    body: VerifyIn, response: Response, db: DB, settings: SettingsDep
) -> Envelope[MeOut]:
    email = read_email_token(body.token, settings)
    user = await db.scalar(select(User).where(User.email == email))
    if user is None:
        raise AppError(400, "token_invalid", "Invalid verification link")
    user.email_verified = True
    await db.commit()
    issue_session(response, user.id, settings)
    return _me(user, await _org_for(db, user))


@router.post("/login")
async def login(
    body: LoginIn,
    request: Request,
    response: Response,
    db: DB,
    redis: RedisDep,
    settings: SettingsDep,
) -> Envelope[MeOut]:
    email = body.email.lower()
    await rate_limit(
        redis, f"login:{_client_ip(request)}:{email}", limit=settings.login_rate_limit_per_min
    )
    user = await db.scalar(select(User).where(User.email == email))
    if not verify_password(user.password_hash if user else None, body.password) or user is None:
        raise AppError(401, "invalid_credentials", "Wrong email or password")
    if not user.email_verified:
        raise AppError(403, "email_not_verified", "Verify your email first")
    issue_session(response, user.id, settings)
    return _me(user, await _org_for(db, user))


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    clear_session(response)


@router.get("/me")
async def me(user: CurrentUser, org: CurrentOrg) -> Envelope[MeOut]:
    return _me(user, org)


@router.patch("/me")
async def update_me(body: MePatch, user: CurrentUser, org: CurrentOrg, db: DB) -> Envelope[MeOut]:
    if body.market is not None:
        user.market = body.market.value
    if body.name is not None:
        user.name = body.name
    await db.commit()
    return _me(user, org)


# -- Google OAuth --------------------------------------------------------------------


def _oauth(request: Request) -> OAuth:
    oauth: OAuth | None = getattr(request.app.state, "oauth", None)
    if oauth is None:
        raise AppError(503, "google_disabled", "Google sign-in is not configured")
    return oauth


GoogleOAuth = Annotated[OAuth, Depends(_oauth)]


@router.get("/google/login", include_in_schema=False)
async def google_login(request: Request, oauth: GoogleOAuth, settings: SettingsDep) -> Any:
    return await oauth.google.authorize_redirect(request, settings.google_redirect_uri)


@router.get("/google/callback", include_in_schema=False)
async def google_callback(
    request: Request, oauth: GoogleOAuth, db: DB, settings: SettingsDep
) -> RedirectResponse:
    fail = RedirectResponse(f"{settings.web_base_url}/login?error=google", status_code=303)
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        log.warning("google oauth failed", exc_info=True)
        return fail
    info = token.get("userinfo") or {}
    if not info.get("email") or not info.get("email_verified"):
        return fail

    user = await _upsert_google_user(db, info)
    await db.commit()
    response = RedirectResponse(f"{settings.web_base_url}/dashboard", status_code=303)
    issue_session(response, user.id, settings)
    return response


async def _upsert_google_user(db: DB, info: dict[str, Any]) -> User:
    sub, email = str(info["sub"]), str(info["email"]).lower()
    user = await db.scalar(select(User).where(User.google_sub == sub))
    if user:
        return user
    user = await db.scalar(select(User).where(User.email == email))
    if user:  # Google verified this email -> safe to link
        user.google_sub = sub
        user.email_verified = True
        return user
    return await create_user_with_org(
        db, email=email, name=info.get("name"), google_sub=sub, email_verified=True
    )


def build_oauth(settings: Settings) -> OAuth | None:
    if not settings.google_oauth_enabled:
        return None
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret.get_secret_value(),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth
