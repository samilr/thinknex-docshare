"""Retención: vence shares y purga snapshots que ya no respaldan ningún share vigente.

El contenido se borra; el hash sha256 permanece en la auditoría como prueba de QUÉ se compartió
(minimización de datos, Ley 21.719).

Regla: un snapshot se purga cuando ningún share que lo referencia está ACTIVE ni venció hace
menos de ``grace_hours`` (margen para soporte o investigación de incidentes).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.adapters.storage import BlobStorage
from app.db.models import Document, Share
from app.domain.enums import ActorType, AuditEventType, ShareStatus
from app.services import audit_service


@dataclass(frozen=True)
class RetentionResult:
    expired_shares: int
    purged_snapshots: int


def expire_overdue(db: Session, now: datetime) -> int:
    overdue = db.scalars(
        select(Share).where(Share.status == ShareStatus.ACTIVE.value, Share.expires_at <= now)
    ).unique()
    count = 0
    for share in overdue:
        share.status = ShareStatus.EXPIRED.value
        audit_service.record(
            db,
            event_type=AuditEventType.SHARE_EXPIRED,
            actor_type=ActorType.SYSTEM,
            share_id=share.id,
            document_id=share.document_id,
            channel=share.channel,
            details={"by": "retention_job"},
        )
        count += 1
    return count


def purge_snapshots(db: Session, storage: BlobStorage, now: datetime, grace_hours: int) -> int:
    cutoff = now - timedelta(hours=grace_hours)
    live_docs = db.scalars(select(Document).where(Document.snapshot_deleted_at.is_(None))).all()
    purged = 0
    for key in sorted({doc.snapshot_key for doc in live_docs}):
        docs_with_key = select(Document.id).where(Document.snapshot_key == key)
        in_use = db.scalar(
            select(
                exists().where(
                    Share.document_id.in_(docs_with_key),
                    or_(Share.status == ShareStatus.ACTIVE.value, Share.expires_at > cutoff),
                )
            )
        )
        if in_use:
            continue
        storage.delete(key)
        for doc in (d for d in live_docs if d.snapshot_key == key):
            doc.snapshot_deleted_at = now
            audit_service.record(
                db,
                event_type=AuditEventType.SNAPSHOT_PURGED,
                actor_type=ActorType.SYSTEM,
                document_id=doc.id,
                details={"sha256": doc.sha256, "grace_hours": grace_hours},
            )
        purged += 1
    return purged


def run(db: Session, storage: BlobStorage, grace_hours: int) -> RetentionResult:
    now = datetime.now(UTC)
    expired = expire_overdue(db, now)
    purged = purge_snapshots(db, storage, now, grace_hours)
    return RetentionResult(expired_shares=expired, purged_snapshots=purged)
