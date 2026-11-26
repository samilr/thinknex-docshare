"""Modelo de datos de share-api. Ver docs/03-modelo-datos.md para el diccionario."""

import uuid
from datetime import UTC, datetime
from typing import Any

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
from sqlalchemy.dialects.postgresql import JSONB
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
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


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
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipients.id"))
    channel: Mapped[str] = mapped_column(String(16))
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
    recipient: Mapped[Recipient] = relationship(lazy="joined")
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
