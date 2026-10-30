"""Passwords, session cookies, CSRF, email tokens, rate limiting.

Session: signed JWT in an httpOnly cookie (`sm_session`), SameSite=Lax.
CSRF: double-submit — readable `sm_csrf` cookie must equal the `X-CSRF-Token` header on
mutating requests. SameSite=Lax already blocks most cross-site POSTs; this is defense in depth.
"""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from redis.asyncio import Redis

from seomaster_api.errors import AppError
from seomaster_core.config import Settings

SESSION_COOKIE = "sm_session"
CSRF_COOKIE = "sm_csrf"
CSRF_HEADER = "x-csrf-token"

_hasher = PasswordHasher()
_DUMMY_HASH = _hasher.hash("timing-equalizer")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def issue_session(response: Response, user_id: uuid.UUID, settings: Settings) -> None:
    now = datetime.now(UTC)
    max_age = settings.session_days * 86400
    token = jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + timedelta(seconds=max_age)},
        settings.auth_secret.get_secret_value(),
        algorithm="HS256",
    )
    common = {"secure": settings.is_prod, "samesite": "lax", "max_age": max_age, "path": "/"}
    response.set_cookie(SESSION_COOKIE, token, httponly=True, **common)  # type: ignore[arg-type]
    response.set_cookie(CSRF_COOKIE, secrets.token_urlsafe(32), httponly=False, **common)  # type: ignore[arg-type]


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")


def read_session(token: str | None, settings: Settings) -> uuid.UUID | None:
    if not token:
        return None
    try:
        claims = jwt.decode(token, settings.auth_secret.get_secret_value(), algorithms=["HS256"])
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def _email_serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.auth_secret.get_secret_value(), salt="verify-email")


def make_email_token(email: str, settings: Settings) -> str:
    return _email_serializer(settings).dumps(email)


def read_email_token(token: str, settings: Settings, max_age_s: int = 2 * 86400) -> str:
    try:
        return str(_email_serializer(settings).loads(token, max_age=max_age_s))
    except SignatureExpired as exc:
        raise AppError(400, "token_expired", "Verification link expired") from exc
    except BadSignature as exc:
        raise AppError(400, "token_invalid", "Invalid verification link") from exc


async def rate_limit(redis: Redis, key: str, limit: int, window_s: int = 60) -> None:
    """Fixed-window limiter. Fails open if Redis is unavailable."""
    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.incr(f"rl:{key}")
            pipe.expire(f"rl:{key}", window_s, nx=True)
            count, _ = await pipe.execute()
    except Exception:
        return
    if int(count) > limit:
        raise AppError(429, "rate_limited", "Too many attempts, try again in a minute")
