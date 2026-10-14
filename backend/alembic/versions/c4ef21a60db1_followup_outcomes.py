"""record human follow-up outcomes

Revision ID: c4ef21a60db1
Revises: ab31dc5f9281
Create Date: 2026-10-15
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c4ef21a60db1"
down_revision: str | Sequence[str] | None = "ab31dc5f9281"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("followups", sa.Column("outcome", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("followups", "outcome")
