"""Postgres app-state tables (doc 03 §6.1). Large/analytical data lives in ClickHouse."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from seomaster_db.base import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # free | pro | agency
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)  # lowercased
    name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(String(255))  # null for Google-only users
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    market: Mapped[str] = mapped_column(String(8), default="in", nullable=False)
    created_at: Mapped[datetime] = _created_at()


class Org(Base):
    __tablename__ = "orgs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"), default="free", nullable=False)
    billing_provider: Mapped[str | None] = mapped_column(String(16))  # stripe | razorpay
    billing_customer_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = _created_at()


class OrgMember(Base):
    __tablename__ = "org_members"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    role: Mapped[str] = mapped_column(String(16), default="owner", nullable=False)


class UsageCounter(Base):
    """Metered usage per org, metric and period key (`2026-11-02`, `2026-11`)."""

    __tablename__ = "usage_counters"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True
    )
    metric: Mapped[str] = mapped_column(String(64), primary_key=True)
    period: Mapped[str] = mapped_column(String(16), primary_key=True)
    used: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("org_id", "domain", "market"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = _created_at()


class KeywordList(Base):
    __tablename__ = "keyword_lists"
    __table_args__ = (UniqueConstraint("org_id", "name"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = _created_at()


class KeywordListItem(Base):
    """Keyword + last known metrics (copied from ClickHouse, refreshed by the volume job)."""

    __tablename__ = "keyword_list_items"
    __table_args__ = (UniqueConstraint("list_id", "keyword"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("keyword_lists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    keyword: Mapped[str] = mapped_column(String(200), nullable=False)
    volume: Mapped[int | None] = mapped_column(Integer)
    kd: Mapped[int | None] = mapped_column(SmallInteger)
    cpc: Mapped[float | None] = mapped_column(Float)
    competition: Mapped[float | None] = mapped_column(Float)
    intents: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    source: Mapped[str | None] = mapped_column(String(32))
    metrics_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    added_at: Mapped[datetime] = _created_at()
