"""Autenticación propia: roles múltiples, estado de login, refresh tokens y bandeja simulada

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    # --- users: role -> roles[] + estado de autenticación ------------------------------
    op.add_column("users", sa.Column("roles", postgresql.ARRAY(sa.String(16)), nullable=True))
    op.execute("UPDATE users SET roles = ARRAY[role]::varchar(16)[]")
    op.alter_column("users", "roles", nullable=False)
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role")
    op.create_check_constraint(
        "ck_users_roles",
        "users",
        "cardinality(roles) > 0 AND roles <@ ARRAY['ADMIN','SHARER','AUDITOR']::varchar(16)[]",
    )
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column(
        "users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true")
    )
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "users",
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("locked_until", TS, nullable=True))
    op.add_column("users", sa.Column("last_login_at", TS, nullable=True))
    op.add_column("users", sa.Column("password_changed_at", TS, nullable=True))
    op.add_column(
        "users", sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now())
    )

    # --- refresh tokens rotativos ------------------------------------------------------
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("revoked_at", TS, nullable=True),
        sa.Column("replaced_by", sa.Uuid(), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_family", "refresh_tokens", ["family_id"])

    # --- bandeja simulada (solo demo) ----------------------------------------------------
    op.create_table(
        "simulated_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("share_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("to_address", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("delivered_real", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_simulated_messages_share_id", "simulated_messages", ["share_id"])
    op.create_index("ix_simulated_messages_created_at", "simulated_messages", ["created_at"])


def downgrade() -> None:
    op.drop_table("simulated_messages")
    op.drop_table("refresh_tokens")
    op.add_column("users", sa.Column("role", sa.String(16), nullable=True))
    op.execute("UPDATE users SET role = roles[1]")
    op.drop_constraint("ck_users_roles", "users", type_="check")
    for column in (
        "roles",
        "password_hash",
        "is_active",
        "must_change_password",
        "failed_login_attempts",
        "locked_until",
        "last_login_at",
        "password_changed_at",
        "updated_at",
    ):
        op.drop_column("users", column)
    op.alter_column("users", "role", nullable=False)
    op.create_check_constraint(
        "ck_users_role", "users", "role IN ('ADMIN','SHARER','AUDITOR')"
    )
