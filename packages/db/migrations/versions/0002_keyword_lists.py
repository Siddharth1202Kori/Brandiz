"""keyword lists + Phase 1 plan limits

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-30
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

from seomaster_db.seed import PLANS

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "keyword_lists",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("market", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("org_id", "name"),
    )
    op.create_index("ix_keyword_lists_org_id", "keyword_lists", ["org_id"])
    op.create_table(
        "keyword_list_items",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "list_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("keyword_lists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("keyword", sa.String(200), nullable=False),
        sa.Column("volume", sa.Integer()),
        sa.Column("kd", sa.SmallInteger()),
        sa.Column("cpc", sa.Float()),
        sa.Column("competition", sa.Float()),
        sa.Column("intents", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source", sa.String(32)),
        sa.Column("metrics_updated_at", sa.DateTime(timezone=True)),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("list_id", "keyword"),
    )
    op.create_index("ix_keyword_list_items_list_id", "keyword_list_items", ["list_id"])

    # Plans already exist from 0001: overwrite limits with the current seed.
    for plan in PLANS:
        op.execute(
            sa.text("UPDATE plans SET limits = CAST(:limits AS jsonb) WHERE id = :id").bindparams(
                limits=json.dumps(plan["limits"]), id=plan["id"]
            )
        )


def downgrade() -> None:
    op.drop_table("keyword_list_items")
    op.drop_table("keyword_lists")
