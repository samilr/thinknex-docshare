"""Eliminación lógica de documentos

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.add_column("documents", sa.Column("deleted_by", sa.String(320)))


def downgrade() -> None:
    op.drop_column("documents", "deleted_by")
    op.drop_column("documents", "deleted_at")
