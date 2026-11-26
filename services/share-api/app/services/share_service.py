"""Caso de uso principal: compartir un documento de forma controlada y auditable."""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.adapters.channels.base import ChannelRegistry
from app.adapters.document_source import DocumentSource, SourceDocument
from app.adapters.storage import BlobStorage, snapshot_key
from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    NotFoundError,
    SensitiveContentError,
    SharingBlockedError,
    UpstreamError,
    ValidationFailedError,
)
from app.core.security import generate_share_token, hash_token, mask_email, mask_phone
from app.db.models import Document, Recipient, Share, User
from app.domain.enums import (
    ActorType,
    AuditEventType,
    Channel,
    Decision,
    NotificationKind,
    ShareStatus,
)
from app.schemas import (
    DocumentOut,
    PrecheckResponse,
    RecipientIn,
    RecipientOut,
    ShareOut,
    ShareRequest,
)
from app.sensitivity.checker import SensitivityChecker, SensitivityReport
from app.services import audit_service, notifications
from app.services.context import RequestContext


@dataclass
class ShareService:
    db: Session
    settings: Settings
    source: DocumentSource
    storage: BlobStorage
    channels: ChannelRegistry
    checker: SensitivityChecker

    # ---------------------------------------------------------------- helpers
    def _is_external(self, recipient: RecipientIn) -> bool:
        """Supuesto: interno = email con dominio corporativo; un teléfono no prueba pertenencia."""
        if recipient.email:
            domain = str(recipient.email).rsplit("@", 1)[-1].lower()
            return domain not in {d.lower() for d in self.settings.internal_email_domains}
        return True

    def _fetch_verified(self, document_id: str) -> tuple[SourceDocument, bytes]:
        meta = self.source.get_metadata(document_id)
        content = self.source.get_content(document_id)
        digest = hashlib.sha256(content).hexdigest()
        if digest != meta.sha256:
            raise UpstreamError(
                "El contenido recibido no coincide con el hash publicado por el DMS"
            )
        return meta, content

    def _analyze(
        self, meta: SourceDocument, content: bytes, is_external: bool
    ) -> SensitivityReport:
        return self.checker.check(
            content=content,
            mime_type=meta.mime_type,
            title=meta.title,
            classification=meta.classification,
            is_external=is_external,
        )

    def _upsert_document(self, meta: SourceDocument, content: bytes) -> Document:
        key = snapshot_key(meta.sha256)
        if not self.storage.exists(key):
            self.storage.put(key, content, meta.mime_type)
        doc = self.db.scalar(
            select(Document).where(Document.source_id == meta.id, Document.sha256 == meta.sha256)
        )
        now = datetime.now(UTC)
        if doc is None:
            doc = Document(
                source_id=meta.id,
                source_version=meta.version,
                title=meta.title,
                mime_type=meta.mime_type,
                size_bytes=meta.size_bytes,
                sha256=meta.sha256,
                classification=meta.classification.value,
                snapshot_key=key,
                fetched_at=now,
            )
            self.db.add(doc)
        else:
            doc.snapshot_deleted_at = None
            doc.fetched_at = now
        self.db.flush()
        return doc

    def _upsert_recipient(self, data: RecipientIn, is_external: bool) -> Recipient:
        email = str(data.email).lower() if data.email else None
        phone = data.phone.replace(" ", "") if data.phone else None
        conditions = []
        if email:
            conditions.append(Recipient.email == email)
        if phone:
            conditions.append(Recipient.phone == phone)
        recipient = self.db.scalar(select(Recipient).where(or_(*conditions)).limit(1))
        if recipient is None:
            recipient = Recipient(name=data.name, email=email, phone=phone, is_external=is_external)
            self.db.add(recipient)
        else:
            recipient.name = data.name
            recipient.email = recipient.email or email
            recipient.phone = recipient.phone or phone
            recipient.is_external = is_external
        self.db.flush()
        return recipient

    # ---------------------------------------------------------------- casos de uso
    def precheck(self, user: User, document_id: str, recipient: RecipientIn) -> PrecheckResponse:
        meta, content = self._fetch_verified(document_id)
        report = self._analyze(meta, content, self._is_external(recipient))
        return PrecheckResponse(document=meta, report=report)

    def create(self, user: User, req: ShareRequest, ctx: RequestContext) -> ShareOut:
        expires_in = req.expires_in_hours or self.settings.default_expiry_hours
        max_accesses = req.max_accesses or self.settings.default_max_accesses
        if expires_in > self.settings.max_expiry_hours:
            raise ValidationFailedError(
                f"expires_in_hours no puede superar {self.settings.max_expiry_hours}"
            )
        if max_accesses > self.settings.max_accesses_limit:
            raise ValidationFailedError(
                f"max_accesses no puede superar {self.settings.max_accesses_limit}"
            )

        is_external = self._is_external(req.recipient)
        meta, content = self._fetch_verified(req.document_id)
        report = self._analyze(meta, content, is_external)
        audit_service.record(
            self.db,
            event_type=AuditEventType.SENSITIVITY_CHECKED,
            actor_type=ActorType.USER,
            actor_id=user.id,
            channel=req.channel,
            ctx=ctx,
            details={
                "source_document_id": meta.id,
                "sha256": meta.sha256,
                **report.audit_summary(),
            },
        )

        if report.decision is Decision.BLOCK:
            audit_service.record(
                self.db,
                event_type=AuditEventType.SHARE_BLOCKED,
                actor_type=ActorType.USER,
                actor_id=user.id,
                channel=req.channel,
                ctx=ctx,
                details={"source_document_id": meta.id, "reasons": report.reasons},
            )
            self.db.commit()  # el intento bloqueado también queda auditado
            raise SharingBlockedError(
                "; ".join(report.reasons), report=report.model_dump(mode="json")
            )
        if report.decision is Decision.WARN and not req.acknowledge_sensitive:
            self.db.commit()
            raise SensitiveContentError(
                "Revise los hallazgos y reenvíe con acknowledge_sensitive=true para confirmar.",
                report=report.model_dump(mode="json"),
            )

        document = self._upsert_document(meta, content)
        recipient = self._upsert_recipient(req.recipient, is_external)
        token = generate_share_token()
        share = Share(
            id=uuid.uuid4(),
            document_id=document.id,
            shared_by=user.id,
            recipient_id=recipient.id,
            channel=req.channel.value,
            reason=req.reason,
            token_hash=hash_token(token),
            status=ShareStatus.ACTIVE.value,
            expires_at=datetime.now(UTC) + timedelta(hours=expires_in),
            max_accesses=max_accesses,
            access_count=0,
            sensitivity_decision=report.decision.value,
            sensitivity_report=report.model_dump(mode="json"),
        )
        self.db.add(share)
        self.db.flush()
        self.db.refresh(share)

        audit_service.record(
            self.db,
            event_type=AuditEventType.SHARE_CREATED,
            actor_type=ActorType.USER,
            actor_id=user.id,
            share_id=share.id,
            document_id=document.id,
            channel=req.channel,
            ctx=ctx,
            details={
                "source_document_id": meta.id,
                "source_version": meta.version,
                "sha256": meta.sha256,
                "recipient_id": str(recipient.id),
                "recipient_external": is_external,
                "reason": req.reason,
                "expires_at": share.expires_at.isoformat(),
                "max_accesses": max_accesses,
                "sensitivity_decision": report.decision.value,
                "sensitive_acknowledged": report.decision is Decision.WARN,
            },
        )

        link = f"{self.settings.public_base_url}/s/{token}"
        result = notifications.send(
            self.db,
            self.channels,
            share,
            kind=NotificationKind.LINK,
            subject=f"{user.name} compartió un documento contigo",
            body=(
                f"Hola {recipient.name},\n\n{user.name} compartió contigo el documento "
                f'"{document.title}".\n\nAccede aquí: {link}\n\n'
                f"Por seguridad te pediremos un código que enviaremos a este mismo medio. "
                f"El enlace vence el {share.expires_at:%Y-%m-%d %H:%M} UTC y permite "
                f"{max_accesses} descarga(s).\n"
            ),
            actor_type=ActorType.SYSTEM,
            actor_id=None,
            ctx=ctx,
        )
        return to_share_out(share, notification_status="SENT" if result.ok else "FAILED")

    def list_own(self, user: User, *, limit: int, offset: int) -> list[ShareOut]:
        shares = self.db.scalars(
            select(Share)
            .where(Share.shared_by == user.id)
            .order_by(Share.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).unique()
        return [to_share_out(s) for s in shares]

    def get_own(self, user: User, share_id: uuid.UUID) -> ShareOut:
        return to_share_out(self._own(user, share_id))

    def _own(self, user: User, share_id: uuid.UUID) -> Share:
        share = self.db.get(Share, share_id)
        if share is None or share.shared_by != user.id:  # 404 también si no es dueño
            raise NotFoundError("Share no encontrado")
        return share

    def revoke(self, user: User, share_id: uuid.UUID, ctx: RequestContext) -> ShareOut:
        share = self._own(user, share_id)
        if share.status != ShareStatus.ACTIVE.value:
            raise ConflictError(f"El share no está activo (estado actual: {share.status})")
        share.status = ShareStatus.REVOKED.value
        share.revoked_at = datetime.now(UTC)
        share.revoked_by = user.id
        audit_service.record(
            self.db,
            event_type=AuditEventType.SHARE_REVOKED,
            actor_type=ActorType.USER,
            actor_id=user.id,
            share_id=share.id,
            document_id=share.document_id,
            channel=share.channel,
            ctx=ctx,
        )
        return to_share_out(share)


def to_share_out(share: Share, notification_status: str | None = None) -> ShareOut:
    recipient = share.recipient
    contact = mask_email(recipient.email) if recipient.email else mask_phone(recipient.phone or "")
    status = ShareStatus(share.status)
    if status is ShareStatus.ACTIVE and share.expires_at <= datetime.now(UTC):
        status = ShareStatus.EXPIRED  # vencimiento perezoso: el estado efectivo se calcula al leer
    return ShareOut(
        id=share.id,
        document=DocumentOut.model_validate(share.document),
        recipient=RecipientOut(
            name=recipient.name, contact=contact, is_external=recipient.is_external
        ),
        shared_by=share.sharer.email,
        channel=Channel(share.channel),
        reason=share.reason,
        status=status,
        created_at=share.created_at,
        expires_at=share.expires_at,
        max_accesses=share.max_accesses,
        access_count=share.access_count,
        sensitivity_decision=Decision(share.sensitivity_decision),
        sensitivity_report=share.sensitivity_report,
        notification_status=notification_status,
        revoked_at=share.revoked_at,
    )
