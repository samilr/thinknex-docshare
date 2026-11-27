"""Enlaces de ThinkNex Docs y permisos: canal LINK, permission, audience

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_shares_channel", "shares", type_="check")
    op.create_check_constraint(
        "ck_shares_channel", "shares", "channel IN ('LINK','EMAIL','WHATSAPP','SMS')"
    )
    op.add_column(
        "shares",
        sa.Column("permission", sa.String(8), nullable=False, server_default="DOWNLOAD"),
    )
    op.add_column(
        "shares",
        sa.Column("audience", sa.String(8), nullable=False, server_default="SPECIFIC"),
    )
    op.create_check_constraint(
        "ck_shares_permission", "shares", "permission IN ('VIEW','DOWNLOAD','EDIT')"
    )
    op.create_check_constraint("ck_shares_audience", "shares", "audience IN ('SPECIFIC','ANYONE')")
    # Un enlace para "cualquiera" no tiene destinatario; uno específico siempre lo tiene.
    op.alter_column("shares", "recipient_id", nullable=True)
    op.create_check_constraint(
        "ck_shares_recipient_audience",
        "shares",
        "(audience = 'ANYONE') OR (recipient_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_shares_anyone_link", "shares", "audience <> 'ANYONE' OR channel = 'LINK'"
    )


def downgrade() -> None:
    op.drop_constraint("ck_shares_anyone_link", "shares", type_="check")
    op.drop_constraint("ck_shares_recipient_audience", "shares", type_="check")
    op.execute("DELETE FROM shares WHERE recipient_id IS NULL")
    op.alter_column("shares", "recipient_id", nullable=False)
    op.drop_constraint("ck_shares_audience", "shares", type_="check")
    op.drop_constraint("ck_shares_permission", "shares", type_="check")
    op.drop_column("shares", "audience")
    op.drop_column("shares", "permission")
    op.drop_constraint("ck_shares_channel", "shares", type_="check")
    op.create_check_constraint(
        "ck_shares_channel", "shares", "channel IN ('EMAIL','WHATSAPP','SMS')"
    )
