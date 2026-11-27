"""Dominio ficticio corporativo: @demo-corp.example -> @thinknex.example

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-27
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

OLD, NEW = "@demo-corp.example", "@thinknex.example"


def upgrade() -> None:
    # Solo cuentas de usuarios internos; la auditoría es inmutable y conserva el valor histórico.
    op.execute(
        f"UPDATE users SET email = replace(email, '{OLD}', '{NEW}') "
        f"WHERE email LIKE '%{OLD}' "
        f"AND replace(email, '{OLD}', '{NEW}') NOT IN (SELECT email FROM users)"
    )
    op.execute(
        f"UPDATE recipients SET email = replace(email, '{OLD}', '{NEW}') WHERE email LIKE '%{OLD}'"
    )


def downgrade() -> None:
    op.execute(
        f"UPDATE users SET email = replace(email, '{NEW}', '{OLD}') WHERE email LIKE '%{NEW}'"
    )
    op.execute(
        f"UPDATE recipients SET email = replace(email, '{NEW}', '{OLD}') WHERE email LIKE '%{NEW}'"
    )
