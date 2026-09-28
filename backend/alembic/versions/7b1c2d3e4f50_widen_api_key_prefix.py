"""widen api_keys.prefix (crm_live_ + 4 chars is 13)

Revision ID: 7b1c2d3e4f50
Revises: 204614c8c511
Create Date: 2026-09-28 20:00:00

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = '7b1c2d3e4f50'
down_revision: str | Sequence[str] | None = '204614c8c511'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table('api_keys') as batch:
        batch.alter_column('prefix', type_=sa.String(length=24), existing_type=sa.String(length=12), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table('api_keys') as batch:
        batch.alter_column('prefix', type_=sa.String(length=12), existing_type=sa.String(length=24), existing_nullable=False)
