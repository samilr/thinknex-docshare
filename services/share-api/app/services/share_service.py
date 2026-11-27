"""Caso de uso principal: compartir un documento de forma controlada y auditable."""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.adapters.channels.base import ChannelRegistry
from app.adapters.document_source import DocumentSource, SourceDocument
from app.adapters.storage import BlobStorage, snapshot_key
from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    SensitiveContentError,
    SharingBlockedError,
    UpstreamError,
    ValidationFailedError,
)
from app.core.security import generate_share_token, hash_token, mask_email, mask_phone
from app.db.models import AuditEvent, Document, Recipient, Share, User
from app.domain.enums import (
    ActorType,
    Audience,
    AuditEventType,
    Channel,
    Classification,
    Decision,
    NotificationKind,
    Permission,
    Role,
    ShareStatus,
)
from app.schemas import (
    DocumentOut,
    PrecheckResponse,
    RecipientIn,
    RecipientOut,
    ShareListPage,
    ShareOut,
    ShareRequest,
    ShareUpdate,
)
from app.sensitivity.checker import SensitivityChecker, SensitivityReport
from app.sensitivity.llm_classifier import LlmSensitivity
from app.services import audit_service, messages, notifications, policy_service
from app.services.context import RequestContext

ShareScope = Literal["mine", "all"]


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
        self,
        meta: SourceDocument,
        content: bytes,
        is_external: bool,
        channel: Channel | None = None,
        audience: Audience = Audience.SPECIFIC,
    ) -> SensitivityReport:
        return self.checker.check(
            content=content,
            mime_type=meta.mime_type,
            title=meta.title,
            classification=meta.classification,
            is_external=is_external,
            rules=policy_service.active_rules(self.db),
            channel=channel.value if channel else None,
            audience=audience.value,
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
    def precheck(
        self,
        user: User,
        document_id: str,
        recipient: RecipientIn | None,
        audience: Audience = Audience.SPECIFIC,
        channel: Channel | None = None,
    ) -> PrecheckResponse:
        meta, content = self._fetch_verified(document_id)
        is_external = audience is Audience.ANYONE or (
            recipient is not None and self._is_external(recipient)
        )
        report = apply_link_policy(
            self._analyze(meta, content, is_external, channel, audience), audience, None
        )
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

        is_external = req.audience is Audience.ANYONE or (
            req.recipient is not None and self._is_external(req.recipient)
        )
        meta, content = self._fetch_verified(req.document_id)
        report = apply_link_policy(
            self._analyze(meta, content, is_external, req.channel, req.audience),
            req.audience,
            req.permission,
        )
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
        recipient = self._upsert_recipient(req.recipient, is_external) if req.recipient else None
        token = generate_share_token()
        share = Share(
            id=uuid.uuid4(),
            document_id=document.id,
            shared_by=user.id,
            recipient_id=recipient.id if recipient else None,
            channel=req.channel.value,
            permission=req.permission.value,
            watermark=req.watermark,
            audience=req.audience.value,
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
                "recipient_id": str(recipient.id) if recipient else None,
                "recipient_external": is_external,
                "audience": req.audience.value,
                "permission": req.permission.value,
                "watermark": req.watermark,
                "reason": req.reason,
                "expires_at": share.expires_at.isoformat(),
                "max_accesses": max_accesses,
                "sensitivity_decision": report.decision.value,
                "sensitive_acknowledged": report.decision is Decision.WARN,
            },
        )

        link = f"{self.settings.public_base_url}/s/{token}"
        if req.channel is Channel.LINK:
            # El emisor copia el enlace y lo envía por el medio que prefiera: se muestra una vez.
            return to_share_out(share, link=link)
        assert recipient is not None  # garantizado por ShareRequest  # noqa: S101
        message = messages.share_link(
            recipient_name=recipient.name,
            sender_name=user.name,
            document_title=document.title,
            link=link,
            expires_at=share.expires_at,
            max_accesses=max_accesses,
            permission=req.permission,
        )
        result = notifications.send(
            self.db,
            self.channels,
            share,
            kind=NotificationKind.LINK,
            subject=message.subject,
            body=message.body,
            actor_type=ActorType.SYSTEM,
            actor_id=None,
            ctx=ctx,
            settings=self.settings,
        )
        return to_share_out(share, notification_status="SENT" if result.ok else "FAILED")

    def update(
        self, user: User, share_id: uuid.UUID, req: ShareUpdate, ctx: RequestContext
    ) -> ShareOut:
        """Edita el acceso de un envío vigente: permiso, vencimiento y accesos permitidos.

        Aplica de inmediato, incluso a sesiones ya abiertas del destinatario (cada solicitud lee
        el permiso desde la BD). Queda auditado con los valores anteriores y nuevos.
        """
        share = self._visible(user, share_id)
        if share.shared_by != user.id and not user.has_any(Role.ADMIN):
            raise ForbiddenError("Solo quien compartió o un ADMIN puede editar el acceso")
        now = datetime.now(UTC)
        if share.status not in (ShareStatus.ACTIVE.value, ShareStatus.EXHAUSTED.value) or (
            share.expires_at <= now
        ):
            raise ConflictError(f"El envío no está vigente (estado actual: {share.status})")

        before = {
            "permission": share.permission,
            "watermark": share.watermark,
            "expires_at": share.expires_at.isoformat(),
            "max_accesses": share.max_accesses,
        }
        if req.permission is not None:
            if req.permission is Permission.EDIT:
                if Audience(share.audience) is Audience.ANYONE:
                    raise ValidationFailedError(
                        "Un enlace para cualquier persona no admite edición"
                    )
                if share.document.classification == Classification.RESTRICTED.value:
                    raise SharingBlockedError(
                        "Los documentos RESTRINGIDOS no admiten edición por destinatarios."
                    )
            share.permission = req.permission.value
        if req.watermark is not None:
            share.watermark = req.watermark
        if req.expires_in_hours is not None:
            if req.expires_in_hours > self.settings.max_expiry_hours:
                raise ValidationFailedError(
                    f"expires_in_hours no puede superar {self.settings.max_expiry_hours}"
                )
            share.expires_at = now + timedelta(hours=req.expires_in_hours)
        if req.max_accesses is not None:
            if req.max_accesses > self.settings.max_accesses_limit:
                raise ValidationFailedError(
                    f"max_accesses no puede superar {self.settings.max_accesses_limit}"
                )
            if req.max_accesses < share.access_count:
                raise ValidationFailedError(
                    f"Ya se usaron {share.access_count} acceso(s): el máximo no puede ser menor"
                )
            share.max_accesses = req.max_accesses
            share.status = (
                ShareStatus.EXHAUSTED.value
                if share.access_count >= share.max_accesses
                else ShareStatus.ACTIVE.value
            )

        after = {
            "permission": share.permission,
            "watermark": share.watermark,
            "expires_at": share.expires_at.isoformat(),
            "max_accesses": share.max_accesses,
        }
        changed = [k for k in before if before[k] != after[k]]
        if changed:
            audit_service.record(
                self.db,
                event_type=AuditEventType.SHARE_UPDATED,
                actor_type=ActorType.USER,
                actor_id=user.id,
                share_id=share.id,
                document_id=share.document_id,
                channel=share.channel,
                ctx=ctx,
                details={
                    "changed": changed,
                    "before": {k: before[k] for k in changed},
                    "after": {k: after[k] for k in changed},
                },
            )
        self.db.flush()
        return to_share_out(share)

    def rotate_link(self, user: User, share_id: uuid.UUID, ctx: RequestContext) -> ShareOut:
        """Genera un enlace nuevo para un envío LINK; el anterior deja de funcionar."""
        share = self._visible(user, share_id)
        if share.shared_by != user.id and not user.has_any(Role.ADMIN):
            raise ForbiddenError("Solo quien compartió o un ADMIN puede generar un enlace nuevo")
        if Channel(share.channel) is not Channel.LINK:
            raise ConflictError("Solo los enlaces de ThinkNex Docs se pueden regenerar")
        if share.status != ShareStatus.ACTIVE.value or share.expires_at <= datetime.now(UTC):
            raise ConflictError("El envío no está activo")
        token = generate_share_token()
        share.token_hash = hash_token(token)
        audit_service.record(
            self.db,
            event_type=AuditEventType.SHARE_LINK_ROTATED,
            actor_type=ActorType.USER,
            actor_id=user.id,
            share_id=share.id,
            document_id=share.document_id,
            channel=share.channel,
            ctx=ctx,
        )
        return to_share_out(share, link=f"{self.settings.public_base_url}/s/{token}")

    def search(
        self,
        user: User,
        *,
        scope: ShareScope,
        status: ShareStatus | None,
        channel: Channel | None,
        document_id: str | None,
        limit: int,
        offset: int,
    ) -> ShareListPage:
        if scope == "all" and not user.has_any(Role.ADMIN, Role.AUDITOR):
            raise ForbiddenError("Solo ADMIN o AUDITOR pueden ver todos los shares")
        stmt = select(Share)
        if scope == "mine":
            stmt = stmt.where(Share.shared_by == user.id)
        if status is ShareStatus.EXPIRED:  # incluye los vencidos aún no marcados (perezoso)
            stmt = stmt.where(
                or_(
                    Share.status == ShareStatus.EXPIRED.value,
                    (Share.status == ShareStatus.ACTIVE.value)
                    & (Share.expires_at <= datetime.now(UTC)),
                )
            )
        elif status is ShareStatus.ACTIVE:
            stmt = stmt.where(
                Share.status == ShareStatus.ACTIVE.value, Share.expires_at > datetime.now(UTC)
            )
        elif status:
            stmt = stmt.where(Share.status == status.value)
        if channel:
            stmt = stmt.where(Share.channel == channel.value)
        if document_id:
            stmt = stmt.join(Document, Share.document_id == Document.id).where(
                Document.source_id == document_id
            )
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        shares = self.db.scalars(
            stmt.order_by(Share.created_at.desc()).limit(limit).offset(offset)
        ).unique()
        return ShareListPage(
            items=[to_share_out(s) for s in shares], total=total, limit=limit, offset=offset
        )

    def _visible(self, user: User, share_id: uuid.UUID) -> Share:
        """Dueño, ADMIN o AUDITOR. Para los demás responde 404 (no revela existencia)."""
        share = self.db.get(Share, share_id)
        if share is None or (
            share.shared_by != user.id and not user.has_any(Role.ADMIN, Role.AUDITOR)
        ):
            raise NotFoundError("Share no encontrado")
        return share

    def get(self, user: User, share_id: uuid.UUID) -> ShareOut:
        return to_share_out(self._visible(user, share_id))

    def timeline(self, user: User, share_id: uuid.UUID) -> list[AuditEvent]:
        share = self._visible(user, share_id)
        rows, _ = audit_service.query(
            self.db, audit_service.AuditFilters(share_id=share.id), limit=500, offset=0
        )
        return list(reversed(rows))

    def revoke(self, user: User, share_id: uuid.UUID, ctx: RequestContext) -> ShareOut:
        share = self._visible(user, share_id)
        if share.shared_by != user.id and not user.has_any(Role.ADMIN):
            raise ForbiddenError("Solo quien compartió o un ADMIN puede revocar")
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
            details={"by_owner": share.shared_by == user.id},
        )
        return to_share_out(share)


def apply_link_policy(
    report: SensitivityReport, audience: Audience, permission: Permission | None
) -> SensitivityReport:
    """Salvaguardas fijas de enlaces y permisos (lo configurable vive en las reglas de política).

    - "Cualquiera con el enlace" no se permite si el contenido no se pudo analizar o si la IA lo
      evaluó como de sensibilidad alta: sin identidad del destinatario no hay a quién advertir.
    - Los documentos RESTRINGIDOS no admiten edición por destinatarios.
    """
    reasons: list[str] = []
    if audience is Audience.ANYONE and (
        not report.text_extracted
        or (report.llm is not None and report.llm.sensitivity is LlmSensitivity.HIGH)
    ):
        reasons.append(
            "No se pudo confirmar que el documento sea apto para un enlace para cualquier "
            "persona. Use 'Persona específica'."
        )
    if permission is Permission.EDIT and report.classification is Classification.RESTRICTED:
        reasons.append("Los documentos RESTRINGIDOS no admiten edición por destinatarios.")
    if not reasons:
        return report
    previous = report.reasons if report.decision is Decision.BLOCK else []
    return report.model_copy(update={"decision": Decision.BLOCK, "reasons": [*previous, *reasons]})


def to_share_out(
    share: Share, notification_status: str | None = None, link: str | None = None
) -> ShareOut:
    recipient = share.recipient
    recipient_out = None
    if recipient is not None:
        contact = (
            mask_email(recipient.email) if recipient.email else mask_phone(recipient.phone or "")
        )
        recipient_out = RecipientOut(
            name=recipient.name, contact=contact, is_external=recipient.is_external
        )
    status = ShareStatus(share.status)
    if status is ShareStatus.ACTIVE and share.expires_at <= datetime.now(UTC):
        status = ShareStatus.EXPIRED  # vencimiento perezoso: el estado efectivo se calcula al leer
    return ShareOut(
        id=share.id,
        document=DocumentOut.model_validate(share.document),
        recipient=recipient_out,
        shared_by=share.sharer.email,
        channel=Channel(share.channel),
        audience=Audience(share.audience),
        permission=Permission(share.permission),
        watermark=share.watermark,
        link=link,
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
