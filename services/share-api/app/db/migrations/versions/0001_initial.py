"""Esquema inicial + protección append-only de audit_events

Revision ID: 0001
Revises:
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint("role IN ('SHARER','AUDITOR')", name="ck_users_role"),
    )
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("classification", sa.String(16), nullable=False),
        sa.Column("snapshot_key", sa.String(200), nullable=False),
        sa.Column("snapshot_deleted_at", TS, nullable=True),
        sa.Column("fetched_at", TS, nullable=False),
        sa.UniqueConstraint("source_id", "sha256", name="uq_documents_source_sha"),
    )
    op.create_table(
        "recipients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("is_external", sa.Boolean(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name="ck_recipient_contact"),
    )
    op.create_table(
        "shares",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("shared_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipient_id", sa.Uuid(), sa.ForeignKey("recipients.id"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("max_accesses", sa.Integer(), nullable=False),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sensitivity_decision", sa.String(8), nullable=False),
        sa.Column("sensitivity_report", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("revoked_at", TS, nullable=True),
        sa.Column("revoked_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("channel IN ('EMAIL','WHATSAPP','SMS')", name="ck_shares_channel"),
        sa.CheckConstraint(
            "status IN ('ACTIVE','REVOKED','EXPIRED','LOCKED','EXHAUSTED')",
            name="ck_shares_status",
        ),
        sa.CheckConstraint(
            "access_count >= 0 AND access_count <= max_accesses", name="ck_shares_access_count"
        ),
    )
    op.create_index("ix_shares_shared_by", "shares", ["shared_by"])
    op.create_table(
        "otp_challenges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("share_id", sa.Uuid(), sa.ForeignKey("shares.id"), nullable=False),
        sa.Column("code_hmac", sa.String(64), nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consumed_at", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_otp_challenges_share", "otp_challenges", ["share_id", "created_at"])
    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("share_id", sa.Uuid(), sa.ForeignKey("shares.id"), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False),
        sa.Column("destination_masked", sa.String(320), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("provider_message_id", sa.String(200), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_notifications_share_id", "notifications", ["share_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("occurred_at", TS, nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=True),
        sa.Column("share_id", sa.Uuid(), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("channel", sa.String(16), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False, unique=True),
    )
    op.create_index("ix_audit_document_time", "audit_events", ["document_id", "occurred_at"])
    op.create_index("ix_audit_actor", "audit_events", ["actor_id"])
    op.create_index("ix_audit_share", "audit_events", ["share_id"])

    # Append-only a nivel de base de datos: ni la propia aplicación puede editar o borrar eventos.
    op.execute(
        """
        CREATE FUNCTION audit_events_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events es append-only: % no permitido', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_update_delete BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION audit_events_append_only();"
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_truncate BEFORE TRUNCATE ON audit_events "
        "FOR EACH STATEMENT EXECUTE FUNCTION audit_events_append_only();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_truncate ON audit_events")
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update_delete ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS audit_events_append_only()")
    for table in (
        "audit_events",
        "notifications",
        "otp_challenges",
        "shares",
        "recipients",
        "documents",
        "users",
    ):
        op.drop_table(table)
