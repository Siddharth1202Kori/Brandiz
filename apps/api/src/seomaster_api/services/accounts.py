"""User + personal workspace creation."""

from sqlalchemy.ext.asyncio import AsyncSession

from seomaster_db.models import Org, OrgMember, User


async def create_user_with_org(
    db: AsyncSession,
    *,
    email: str,
    name: str | None,
    password_hash: str | None = None,
    google_sub: str | None = None,
    email_verified: bool = False,
) -> User:
    user = User(
        email=email.lower(),
        name=name,
        password_hash=password_hash,
        google_sub=google_sub,
        email_verified=email_verified,
    )
    org = Org(name=f"{name or email.split('@')[0]}'s workspace", plan_id="free")
    db.add_all([user, org])
    await db.flush()
    db.add(OrgMember(org_id=org.id, user_id=user.id, role="owner"))
    await db.flush()
    return user
