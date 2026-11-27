"""Sistema documental: bibliotecas, carpetas, documentos y versiones

Revision ID: 0001
Revises:
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "libraries",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_table(
        "folders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("library_id", sa.String(40), sa.ForeignKey("libraries.id"), nullable=False),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("folders.id"), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_by", sa.String(320), nullable=False),
        sa.Column("created_at", TS, nullable=False),
    )
    op.create_index("ix_folders_library_parent", "folders", ["library_id", "parent_id"])
    op.create_table(
        "documents",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("library_id", sa.String(40), sa.ForeignKey("libraries.id"), nullable=False),
        sa.Column("folder_id", sa.String(36), sa.ForeignKey("folders.id"), nullable=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("classification", sa.String(16), nullable=False),
        sa.Column("owner", sa.String(320), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(320), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint(
            "classification IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')",
            name="ck_documents_classification",
        ),
    )
    op.create_index("ix_documents_location", "documents", ["library_id", "folder_id"])
    op.create_table(
        "document_versions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.String(40), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(200), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(320), nullable=False),
        sa.Column("created_at", TS, nullable=False),
        sa.UniqueConstraint("document_id", "version", name="uq_document_version"),
    )


def downgrade() -> None:
    for table in ("document_versions", "documents", "folders", "libraries"):
        op.drop_table(table)
