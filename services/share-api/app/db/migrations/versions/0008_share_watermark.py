"""Marca de agua opcional por envío

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shares",
        sa.Column("watermark", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("shares", "watermark")
