"""lead priority history and explicit contact preference fields

Revision ID: ab31dc5f9281
Revises: 7b1c2d3e4f50
Create Date: 2026-10-15
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ab31dc5f9281"
down_revision: str | Sequence[str] | None = "7b1c2d3e4f50"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("preferred_contact_channel", sa.String(length=16), nullable=True))
    op.add_column("leads", sa.Column("preferred_contact_window", sa.String(length=80), nullable=True))
    op.add_column("leads", sa.Column("whatsapp_call_consent", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("leads", sa.Column("consent_recorded_at", sa.DateTime(), nullable=True))
    # Existing consent flags have no provenance or timestamp, so they cannot authorize new outreach.
    op.execute(sa.text("UPDATE leads SET consent_marketing = false"))
    op.create_table(
        "lead_score_history",
        sa.Column("agency_id", sa.String(length=36), nullable=False),
        sa.Column("lead_id", sa.String(length=36), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("band", sa.String(length=8), nullable=False),
        sa.Column("stage", sa.String(length=24), nullable=False),
        sa.Column("factors", sa.JSON(), nullable=False),
        sa.Column("trigger", sa.String(length=40), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["agency_id"], ["agencies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lead_score_history_agency_id", "lead_score_history", ["agency_id"])
    op.create_index("ix_lead_score_history_lead_id", "lead_score_history", ["lead_id"])
    op.create_index("ix_score_history_lead_created", "lead_score_history", ["lead_id", "created_at"])
    op.create_index("ix_lead_score_history_updated_at", "lead_score_history", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_lead_score_history_updated_at", table_name="lead_score_history")
    op.drop_index("ix_score_history_lead_created", table_name="lead_score_history")
    op.drop_index("ix_lead_score_history_lead_id", table_name="lead_score_history")
    op.drop_index("ix_lead_score_history_agency_id", table_name="lead_score_history")
    op.drop_table("lead_score_history")
    op.drop_column("leads", "consent_recorded_at")
    op.drop_column("leads", "whatsapp_call_consent")
    op.drop_column("leads", "preferred_contact_window")
    op.drop_column("leads", "preferred_contact_channel")
