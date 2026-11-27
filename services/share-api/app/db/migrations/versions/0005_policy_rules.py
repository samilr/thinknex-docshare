"""Política configurable: tabla policy_rules con las reglas por defecto

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-27
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

ALL_FINDINGS = ["RUT", "EMAIL", "PHONE", "CARD", "BANK_ACCOUNT"]
SEED = [
    (
        "Restringidos fuera de la organización",
        "BLOCK",
        "Documento RESTRICTED: no puede compartirse con destinatarios externos.",
        ["RESTRICTED"],
        "EXTERNAL",
        [],
    ),
    (
        "Restringidos entre áreas",
        "WARN",
        "Documento RESTRICTED: requiere confirmación incluso entre áreas internas.",
        ["RESTRICTED"],
        "INTERNAL",
        [],
    ),
    (
        "Confidenciales a externos",
        "WARN",
        "Documento CONFIDENTIAL dirigido a un destinatario externo.",
        ["CONFIDENTIAL"],
        "EXTERNAL",
        [],
    ),
    (
        "Datos personales a externos",
        "WARN",
        "Contiene datos personales o financieros y sale de la organización.",
        [],
        "EXTERNAL",
        ALL_FINDINGS,
    ),
]


def upgrade() -> None:
    table = op.create_table(
        "policy_rules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("message", sa.String(300), nullable=False),
        sa.Column("classifications", postgresql.ARRAY(sa.String(16)), nullable=False),
        sa.Column("recipient", sa.String(8), nullable=False, server_default="ANY"),
        sa.Column("finding_types", postgresql.ARRAY(sa.String(16)), nullable=False),
        sa.Column("channels", postgresql.ARRAY(sa.String(16)), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(320), nullable=False),
        sa.Column("updated_by", sa.String(320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("action IN ('WARN','BLOCK')", name="ck_policy_rules_action"),
        sa.CheckConstraint(
            "recipient IN ('ANY','INTERNAL','EXTERNAL')", name="ck_policy_rules_recipient"
        ),
    )
    now = datetime.now(UTC)
    op.bulk_insert(
        table,
        [
            {
                "id": uuid.uuid4(),
                "name": name,
                "description": "Regla inicial (equivalente a la política original).",
                "action": action,
                "message": message,
                "classifications": classifications,
                "recipient": recipient,
                "finding_types": findings,
                "channels": [],
                "enabled": True,
                "created_by": "sistema",
                "updated_by": "sistema",
                "created_at": now,
                "updated_at": now,
            }
            for name, action, message, classifications, recipient, findings in SEED
        ],
    )


def downgrade() -> None:
    op.drop_table("policy_rules")
