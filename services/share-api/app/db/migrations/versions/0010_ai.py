"""IA: pgvector, índice de documentos, fragmentos con embeddings, cola y uso

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-27
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "ai_index",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_document_id", sa.String(100), nullable=False, index=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("library_id", sa.String(40)),
        sa.Column("folder_id", sa.String(40)),
        sa.Column("classification", sa.String(16), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(10), nullable=False, server_default="PENDING"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(500)),
        sa.Column("embedding_model", sa.String(80)),
        sa.Column("summary", sa.Text()),
        sa.Column("suggested_classification", sa.String(16)),
        sa.Column("suggestion_reason", sa.String(500)),
        sa.Column("indexed_at", TS),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("source_document_id", "sha256", name="uq_ai_index_doc_sha"),
        sa.CheckConstraint(
            "status IN ('PENDING','INDEXED','EMPTY','SKIPPED','FAILED')", name="ck_ai_index_status"
        ),
    )
    op.create_table(
        "ai_chunks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "index_id",
            sa.BigInteger(),
            sa.ForeignKey("ai_index.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_from", sa.Integer(), nullable=False),
        sa.Column("page_to", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        sa.Column(
            "tsv",
            sa.dialects.postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('spanish', text)", persisted=True),
        ),
    )
    op.execute(
        "CREATE INDEX ix_ai_chunks_embedding ON ai_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX ix_ai_chunks_tsv ON ai_chunks USING gin (tsv)")
    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_document_id", sa.String(100), nullable=False, index=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500)),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_ai_jobs_pending ON ai_jobs (source_document_id) "
        "WHERE status = 'PENDING'"
    )
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Uuid(), index=True),
        sa.Column("feature", sa.String(40), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("ai_usage")
    op.drop_table("ai_jobs")
    op.drop_table("ai_chunks")
    op.drop_table("ai_index")
