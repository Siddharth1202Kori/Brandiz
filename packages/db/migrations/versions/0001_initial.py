"""initial: plans, users, orgs, members, usage counters, projects

Revision ID: 0001
Revises:
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from seomaster_db.seed import PLANS

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")


def upgrade() -> None:
    plans = op.create_table(
        "plans",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("limits", pg.JSONB(), nullable=False),
    )
    op.bulk_insert(plans, PLANS)

    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("name", sa.String(200)),
        sa.Column("password_hash", sa.String(255)),
        sa.Column("google_sub", sa.String(64), unique=True),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("market", sa.String(8), nullable=False, server_default="in"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_table(
        "orgs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column(
            "plan_id",
            sa.String(32),
            sa.ForeignKey("plans.id"),
            nullable=False,
            server_default="free",
        ),
        sa.Column("billing_provider", sa.String(16)),
        sa.Column("billing_customer_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_table(
        "org_members",
        sa.Column(
            "org_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(16), nullable=False, server_default="owner"),
    )
    op.create_index("ix_org_members_user_id", "org_members", ["user_id"])
    op.create_table(
        "usage_counters",
        sa.Column(
            "org_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("metric", sa.String(64), primary_key=True),
        sa.Column("period", sa.String(16), primary_key=True),
        sa.Column("used", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.create_table(
        "projects",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("org_id", "domain", "market"),
    )
    op.create_index("ix_projects_org_id", "projects", ["org_id"])


def downgrade() -> None:
    for table in ("projects", "usage_counters", "org_members", "orgs", "users", "plans"):
        op.drop_table(table)
