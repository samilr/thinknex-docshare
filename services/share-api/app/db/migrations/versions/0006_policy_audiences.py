"""Reglas por audiencia: la salvaguarda de "cualquiera con el enlace" pasa a ser editable

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-27
"""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

NAMES = (
    "Enlace para cualquiera con datos personales",
    "Enlace para cualquiera con documentos confidenciales",
)


def upgrade() -> None:
    op.add_column(
        "policy_rules",
        sa.Column(
            "audiences",
            postgresql.ARRAY(sa.String(16)),
            nullable=False,
            server_default="{}",
        ),
    )
    rules = sa.table(
        "policy_rules",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("action", sa.String()),
        sa.column("message", sa.String()),
        sa.column("classifications", postgresql.ARRAY(sa.String())),
        sa.column("recipient", sa.String()),
        sa.column("finding_types", postgresql.ARRAY(sa.String())),
        sa.column("channels", postgresql.ARRAY(sa.String())),
        sa.column("audiences", postgresql.ARRAY(sa.String())),
        sa.column("enabled", sa.Boolean()),
        sa.column("created_by", sa.String()),
        sa.column("updated_by", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(UTC)
    base = {
        "description": "Regla inicial.",
        "action": "BLOCK",
        "recipient": "ANY",
        "channels": [],
        "audiences": ["ANYONE"],
        "enabled": True,
        "created_by": "sistema",
        "updated_by": "sistema",
        "created_at": now,
        "updated_at": now,
    }
    op.bulk_insert(
        rules,
        [
            {
                **base,
                "id": uuid.uuid4(),
                "name": NAMES[0],
                "message": "Un enlace para cualquier persona no puede incluir datos personales. "
                "Use 'Persona específica'.",
                "classifications": [],
                "finding_types": ["RUT", "EMAIL", "PHONE", "CARD", "BANK_ACCOUNT"],
            },
            {
                **base,
                "id": uuid.uuid4(),
                "name": NAMES[1],
                "message": "Los documentos confidenciales o restringidos no se comparten con un "
                "enlace para cualquier persona.",
                "classifications": ["CONFIDENTIAL", "RESTRICTED"],
                "finding_types": [],
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM policy_rules WHERE name IN :names").bindparams(
            sa.bindparam("names", expanding=True, value=list(NAMES))
        )
    )
    op.drop_column("policy_rules", "audiences")
