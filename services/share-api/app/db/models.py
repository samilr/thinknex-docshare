"""Modelo de datos de share-api. Ver docs/03-modelo-datos.md para el diccionario."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True), dict[str, Any]: JSONB}  # noqa: RUF012


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    roles: Mapped[list[str]] = mapped_column(ARRAY(String(16)))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    must_change_password: Mapped[bool] = mapped_column(default=False)
    failed_login_attempts: Mapped[int] = mapped_column(default=0)
    locked_until: Mapped[datetime | None]
    last_login_at: Mapped[datetime | None]
    password_changed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    def has_any(self, *roles: str) -> bool:
        return any(role in self.roles for role in roles)


class RefreshToken(Base):
    """Refresh token opaco y rotativo. Se guarda solo su hash; ``family_id`` agrupa la cadena
    de rotaciones de una sesión para revocarla completa si se detecta reutilización."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_family", "family_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    family_id: Mapped[uuid.UUID]
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    replaced_by: Mapped[uuid.UUID | None]
    # ADMIN que actúa como ``user_id`` (suplantación auditada); nulo en una sesión normal.
    impersonator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class SimulatedMessage(Base):
    """Bandeja simulada (SOLO DEMO): guarda el mensaje completo, incluido enlace u OTP."""

    __tablename__ = "simulated_messages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    share_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    channel: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(8))
    to_address: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    delivered_real: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class Document(Base):
    """Snapshot inmutable de un documento del DMS en el momento de compartirlo."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("source_id", "sha256", name="uq_documents_source_sha"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    source_id: Mapped[str] = mapped_column(String(100))
    source_version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))
    classification: Mapped[str] = mapped_column(String(16))
    snapshot_key: Mapped[str] = mapped_column(String(200))
    snapshot_deleted_at: Mapped[datetime | None]
    fetched_at: Mapped[datetime] = mapped_column(default=utcnow)


class Recipient(Base):
    __tablename__ = "recipients"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(32))
    is_external: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Share(Base):
    __tablename__ = "shares"
    __table_args__ = (Index("ix_shares_shared_by", "shared_by"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    shared_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recipients.id"))
    channel: Mapped[str] = mapped_column(String(16))
    permission: Mapped[str] = mapped_column(String(8), default="DOWNLOAD")
    # Token cifrado (AES-GCM) para volver a mostrar el enlace a quien compartió.
    token_encrypted: Mapped[str | None] = mapped_column(Text)
    # Marca de agua con la identidad del destinatario en el visor y en la descarga.
    watermark: Mapped[bool] = mapped_column(default=True)
    audience: Mapped[str] = mapped_column(String(8), default="SPECIFIC")
    reason: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16))
    expires_at: Mapped[datetime]
    max_accesses: Mapped[int]
    access_count: Mapped[int] = mapped_column(default=0)
    sensitivity_decision: Mapped[str] = mapped_column(String(8))
    sensitivity_report: Mapped[dict[str, Any]]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    revoked_at: Mapped[datetime | None]
    revoked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    document: Mapped[Document] = relationship(lazy="joined")
    recipient: Mapped[Recipient | None] = relationship(lazy="joined")
    sharer: Mapped[User] = relationship(foreign_keys=[shared_by], lazy="joined")


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"
    __table_args__ = (Index("ix_otp_challenges_share", "share_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    share_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shares.id"))
    code_hmac: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime]
    attempts: Mapped[int] = mapped_column(default=0)
    consumed_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    share_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shares.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    destination_masked: Mapped[str] = mapped_column(String(320))
    kind: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(8))
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class AuditEvent(Base):
    """Registro append-only encadenado por hash. Un trigger en BD impide UPDATE/DELETE."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_document_time", "document_id", "occurred_at"),
        Index("ix_audit_actor", "actor_id"),
        Index("ix_audit_share", "share_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime]
    event_type: Mapped[str] = mapped_column(String(32))
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_id: Mapped[str | None] = mapped_column(String(64))
    share_id: Mapped[uuid.UUID | None]
    document_id: Mapped[uuid.UUID | None]
    channel: Mapped[str | None] = mapped_column(String(16))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class PolicyRuleRow(Base):
    """Regla de la política de compartición, administrada por un ADMIN (ver sensitivity/policy)."""

    __tablename__ = "policy_rules"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    action: Mapped[str] = mapped_column(String(8))
    message: Mapped[str] = mapped_column(String(300))
    classifications: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    recipient: Mapped[str] = mapped_column(String(8), default="ANY")
    finding_types: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    channels: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    audiences: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    enabled: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[str] = mapped_column(String(320))
    updated_by: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AiIndex(Base):
    """Estado del índice de IA de una versión de un documento (por sha256 de su contenido).

    La versión vigente tiene ``is_current``; las anteriores se conservan mientras haya snapshots
    compartidos que las usen (las preguntas del destinatario consultan su snapshot).
    """

    __tablename__ = "ai_index"
    __table_args__ = (UniqueConstraint("source_document_id", "sha256", name="uq_ai_index_doc_sha"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_document_id: Mapped[str] = mapped_column(String(100), index=True)
    sha256: Mapped[str] = mapped_column(String(64))
    version: Mapped[int]
    title: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(200))
    mime_type: Mapped[str] = mapped_column(String(120))
    library_id: Mapped[str | None] = mapped_column(String(40))
    folder_id: Mapped[str | None] = mapped_column(String(40))
    classification: Mapped[str] = mapped_column(String(16))
    is_current: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(10), default="PENDING")
    chunk_count: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(String(500))
    embedding_model: Mapped[str | None] = mapped_column(String(80))
    summary: Mapped[str | None] = mapped_column(Text)
    suggested_classification: Mapped[str | None] = mapped_column(String(16))
    suggestion_reason: Mapped[str | None] = mapped_column(String(500))
    indexed_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AiChunk(Base):
    __tablename__ = "ai_chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    index_id: Mapped[int] = mapped_column(ForeignKey("ai_index.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int]
    page_from: Mapped[int]
    page_to: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(768))


class AiJob(Base):
    """Cola de sincronización del índice (outbox): un pendiente por documento a la vez."""

    __tablename__ = "ai_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_document_id: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(10), default="PENDING")
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class AiUsage(Base):
    """Consumo de modelos por usuario y función (costos y presupuesto diario)."""

    __tablename__ = "ai_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    feature: Mapped[str] = mapped_column(String(40))
    model: Mapped[str] = mapped_column(String(80))
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    cache_read_tokens: Mapped[int] = mapped_column(default=0)
    latency_ms: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)
