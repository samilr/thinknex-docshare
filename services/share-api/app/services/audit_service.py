"""Auditoría append-only con cadena de hashes (tamper-evident).

hash_n = sha256(hash_{n-1} || json_canónico(evento_n))

Si alguien altera, borra o reordena un evento (por ejemplo con acceso directo a la BD y el
trigger deshabilitado), ``verify`` detecta el primer eslabón roto. Las inserciones se
serializan con un advisory lock transaccional para mantener la cadena lineal.
"""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, or_, select, text
from sqlalchemy.orm import Session

from app.core.security import mask_email, mask_phone
from app.db.models import AuditEvent, Document, Recipient, User
from app.domain.enums import ActorType, AuditEventType, Channel
from app.services.context import RequestContext

GENESIS_HASH = "0" * 64
_AUDIT_LOCK_KEY = 7_412_903  # identificador arbitrario del advisory lock de la cadena


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="microseconds")


def compute_hash(prev_hash: str, event: AuditEvent) -> str:
    payload = {
        "occurred_at": _iso(event.occurred_at),
        "event_type": event.event_type,
        "actor_type": event.actor_type,
        "actor_id": event.actor_id,
        "share_id": str(event.share_id) if event.share_id else None,
        "document_id": str(event.document_id) if event.document_id else None,
        "channel": event.channel,
        "ip": event.ip,
        "user_agent": event.user_agent,
        "metadata": event.details,
    }
    return hashlib.sha256(prev_hash.encode() + _canonical(payload)).hexdigest()


def _with_request_id(details: dict[str, Any] | None, ctx: RequestContext | None) -> dict[str, Any]:
    merged = dict(details or {})
    if ctx and ctx.request_id:
        merged["request_id"] = ctx.request_id
    return merged


def record(
    db: Session,
    *,
    event_type: AuditEventType,
    actor_type: ActorType,
    actor_id: str | uuid.UUID | None = None,
    share_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    channel: Channel | str | None = None,
    ctx: RequestContext | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _AUDIT_LOCK_KEY})
    prev_hash = db.scalar(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1))
    event = AuditEvent(
        occurred_at=datetime.now(UTC),
        event_type=event_type.value,
        actor_type=actor_type.value,
        actor_id=str(actor_id) if actor_id else None,
        share_id=share_id,
        document_id=document_id,
        channel=str(channel) if channel else None,
        ip=ctx.ip if ctx else None,
        user_agent=ctx.user_agent[:512] if ctx and ctx.user_agent else None,
        details=_with_request_id(details, ctx),
        prev_hash=prev_hash or GENESIS_HASH,
    )
    event.hash = compute_hash(event.prev_hash, event)
    db.add(event)
    db.flush()
    return event


@dataclass(frozen=True)
class AuditFilters:
    document_id: uuid.UUID | None = None
    source_document_id: str | None = None
    share_id: uuid.UUID | None = None
    actor_id: str | None = None
    channel: Channel | None = None
    event_type: AuditEventType | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None


def _apply(stmt: Select[Any], f: AuditFilters) -> Select[Any]:
    if f.document_id:
        stmt = stmt.where(AuditEvent.document_id == f.document_id)
    if f.source_document_id:
        # Incluye eventos previos al snapshot (chequeos de sensibilidad, intentos bloqueados).
        ids = select(Document.id).where(Document.source_id == f.source_document_id)
        stmt = stmt.where(
            or_(
                AuditEvent.document_id.in_(ids),
                AuditEvent.details["source_document_id"].astext == f.source_document_id,
            )
        )
    if f.share_id:
        stmt = stmt.where(AuditEvent.share_id == f.share_id)
    if f.actor_id:
        stmt = stmt.where(AuditEvent.actor_id == f.actor_id)
    if f.channel:
        stmt = stmt.where(AuditEvent.channel == f.channel.value)
    if f.event_type:
        stmt = stmt.where(AuditEvent.event_type == f.event_type.value)
    if f.occurred_from:
        stmt = stmt.where(AuditEvent.occurred_at >= f.occurred_from)
    if f.occurred_to:
        stmt = stmt.where(AuditEvent.occurred_at < f.occurred_to)
    return stmt


def query(
    db: Session, filters: AuditFilters, *, limit: int, offset: int
) -> tuple[list[AuditEvent], int]:
    total = db.scalar(_apply(select(func.count(AuditEvent.id)), filters)) or 0
    rows = db.scalars(
        _apply(select(AuditEvent), filters)
        .order_by(AuditEvent.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def actor_labels(db: Session, events: list[AuditEvent]) -> dict[str, str]:
    """Resuelve actor_id -> etiqueta legible ("quién"): email del usuario o contacto enmascarado."""
    ids_by_type: dict[str, set[uuid.UUID]] = {}
    for event in events:
        if event.actor_id and event.actor_type in (ActorType.USER, ActorType.RECIPIENT):
            ids_by_type.setdefault(event.actor_type, set()).add(uuid.UUID(event.actor_id))
    labels: dict[str, str] = {}
    if users := ids_by_type.get(ActorType.USER):
        for user in db.scalars(select(User).where(User.id.in_(users))):
            labels[str(user.id)] = f"{user.name} <{user.email}>"
    if recipients := ids_by_type.get(ActorType.RECIPIENT):
        for r in db.scalars(select(Recipient).where(Recipient.id.in_(recipients))):
            contact = mask_email(r.email) if r.email else mask_phone(r.phone or "")
            labels[str(r.id)] = f"{r.name} <{contact}>"
    return labels


@dataclass(frozen=True)
class ChainVerification:
    valid: bool
    events_checked: int
    first_broken_event_id: int | None
    last_hash: str


def verify_chain(db: Session) -> ChainVerification:
    expected_prev = GENESIS_HASH
    checked = 0
    stmt = select(AuditEvent).order_by(AuditEvent.id).execution_options(yield_per=500)
    for event in db.scalars(stmt):
        if event.prev_hash != expected_prev or compute_hash(event.prev_hash, event) != event.hash:
            return ChainVerification(False, checked, event.id, expected_prev)
        expected_prev = event.hash
        checked += 1
    return ChainVerification(True, checked, None, expected_prev)
