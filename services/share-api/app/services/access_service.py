"""Flujo del destinatario en el visor de ThinkNex Docs.

1. Abrir el enlace: información previa (sin revelar el documento a una persona no verificada).
2. Iniciar sesión de acceso:
   - Persona específica: código (OTP) al email o teléfono del destinatario.
   - Cualquiera con el enlace: apertura directa (solo documentos sin datos sensibles).
   Cada sesión consume un acceso del máximo permitido.
3. Usar el documento según el permiso:
   - VIEW: páginas renderizadas como imágenes con marca de agua (nunca el archivo original).
   - DOWNLOAD: además, descarga del PDF con marca de agua.
   - EDIT: trabaja sobre el archivo vivo del DMS y puede publicar nuevas versiones.

Toda denegación se audita con su causa real, pero hacia afuera la respuesta es uniforme
(``LinkUnavailableError``) para no revelar si un enlace existe ni por qué dejó de servir.
"""

import hashlib
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.adapters import render
from app.adapters.channels.base import ChannelRegistry
from app.adapters.document_source import DocumentSource, UploadedFile
from app.adapters.storage import BlobStorage
from app.adapters.watermark import apply_watermark
from app.core.config import Settings
from app.core.errors import (
    ConflictError,
    ForbiddenError,
    InvalidOtpError,
    LinkUnavailableError,
    TooManyRequestsError,
    UpstreamError,
    ValidationFailedError,
)
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    generate_otp,
    hash_token,
    otp_mac,
    verify_otp,
)
from app.db.models import OtpChallenge, Share
from app.domain.enums import (
    ActorType,
    Audience,
    AuditEventType,
    NotificationKind,
    Permission,
    ShareStatus,
)
from app.sensitivity.detectors import FindingSummary, detect, extract_text, summarize
from app.services import audit_service, messages, notifications
from app.services.context import RequestContext

# Estados en los que una sesión YA iniciada sigue siendo válida (agotar accesos no la corta).
_SESSION_OK = {ShareStatus.ACTIVE.value, ShareStatus.EXHAUSTED.value}


@dataclass(frozen=True)
class AccessInfo:
    shared_by: str
    audience: Audience
    permission: Permission
    requires_code: bool
    destination: str | None
    document_title: str | None
    expires_at: datetime


@dataclass(frozen=True)
class OtpIssued:
    sent_to: str
    expires_in_seconds: int


@dataclass(frozen=True)
class AccessSession:
    access_token: str
    expires_in: int
    remaining_accesses: int


@dataclass(frozen=True)
class DocumentView:
    title: str
    mime_type: str
    kind: str
    version: int
    live: bool
    page_count: int
    permission: Permission
    can_download: bool
    can_edit: bool
    viewer_label: str


@dataclass(frozen=True)
class Payload:
    content: bytes
    filename: str
    mime_type: str


@dataclass(frozen=True)
class VersionPublished:
    version: int
    findings: list[FindingSummary]


def _safe_filename(title: str, ext: str) -> str:
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    stem = "".join(c if c.isalnum() or c in "-_ " else "_" for c in ascii_title)[:80]
    return f"{stem or 'documento'}.{ext}"


@dataclass
class AccessService:
    db: Session
    settings: Settings
    storage: BlobStorage
    channels: ChannelRegistry
    source: DocumentSource

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _actor(share: Share) -> str | None:
        return str(share.recipient_id) if share.recipient_id else None

    def _audit(
        self,
        share: Share,
        event: AuditEventType,
        ctx: RequestContext | None,
        actor_type: ActorType = ActorType.RECIPIENT,
        **details: Any,
    ) -> None:
        audit_service.record(
            self.db,
            event_type=event,
            actor_type=actor_type,
            actor_id=self._actor(share) if actor_type is ActorType.RECIPIENT else None,
            share_id=share.id,
            document_id=share.document_id,
            channel=share.channel,
            ctx=ctx,
            details=details or None,
        )

    def _deny(self, share: Share | None, ctx: RequestContext, reason: str) -> LinkUnavailableError:
        audit_service.record(
            self.db,
            event_type=AuditEventType.ACCESS_DENIED,
            actor_type=ActorType.RECIPIENT,
            actor_id=self._actor(share) if share else None,
            share_id=share.id if share else None,
            document_id=share.document_id if share else None,
            channel=share.channel if share else None,
            ctx=ctx,
            details={"reason": reason},
        )
        self.db.commit()  # la denegación debe persistir aunque la request termine en error
        return LinkUnavailableError()

    def _find(self, token: str, ctx: RequestContext) -> Share:
        share = self.db.scalar(select(Share).where(Share.token_hash == hash_token(token)))
        if share is None:
            raise self._deny(None, ctx, "UNKNOWN_TOKEN")
        if share.status == ShareStatus.ACTIVE.value and share.expires_at <= datetime.now(UTC):
            share.status = ShareStatus.EXPIRED.value
            self._audit(share, AuditEventType.SHARE_EXPIRED, None, ActorType.SYSTEM)
        return share

    def _load_usable(self, token: str, ctx: RequestContext) -> Share:
        """Para iniciar una sesión: el envío debe estar activo."""
        share = self._find(token, ctx)
        if share.status != ShareStatus.ACTIVE.value:
            raise self._deny(share, ctx, share.status)
        return share

    def _session(self, token: str, access_token: str, ctx: RequestContext) -> Share:
        """Para usar el documento: sesión válida ligada a este envío."""
        share = self._find(token, ctx)
        try:
            claims = decode_access_token(access_token, self.settings.jwt_secret.get_secret_value())
        except InvalidTokenError:
            raise self._deny(share, ctx, "INVALID_SESSION") from None
        if claims["sub"] != str(share.id):
            raise self._deny(share, ctx, "SESSION_SHARE_MISMATCH")
        if share.status not in _SESSION_OK:
            raise self._deny(share, ctx, share.status)
        return share

    def _consume_access(self, share: Share, ctx: RequestContext) -> AccessSession:
        """Cada sesión consume un acceso (atómico: nunca se supera el máximo)."""
        new_count = self.db.scalar(
            update(Share)
            .where(
                Share.id == share.id,
                Share.status == ShareStatus.ACTIVE.value,
                Share.access_count < Share.max_accesses,
                Share.expires_at > func.now(),
            )
            .values(access_count=Share.access_count + 1)
            .returning(Share.access_count)
        )
        if new_count is None:
            raise self._deny(share, ctx, "NO_ACCESSES_LEFT")
        if new_count >= share.max_accesses:
            self.db.execute(
                update(Share).where(Share.id == share.id).values(status=ShareStatus.EXHAUSTED.value)
            )
        ttl = self.settings.access_token_ttl_minutes
        return AccessSession(
            access_token=create_access_token(
                share.id, self.settings.jwt_secret.get_secret_value(), ttl
            ),
            expires_in=ttl * 60,
            remaining_accesses=share.max_accesses - new_count,
        )

    def _viewer_label(self, share: Share) -> str:
        if share.recipient is not None:
            return share.recipient.name
        return "Enlace público"

    def _stamp(self, share: Share, mode: str) -> str:
        return (
            f"{mode} {self._viewer_label(share)} · {datetime.now(UTC):%Y-%m-%d %H:%M} UTC · "
            f"ref {str(share.id)[:8]}"
        )

    def _content(self, share: Share) -> tuple[bytes, str, str, int, bool]:
        """(contenido, mime, título, versión, vivo). EDIT usa la versión vigente del DMS."""
        document = share.document
        if Permission(share.permission) is Permission.EDIT:
            meta = self.source.get_metadata(document.source_id)
            data = self.source.get_content(document.source_id)
            if hashlib.sha256(data).hexdigest() != meta.sha256:
                raise UpstreamError("El contenido no coincide con el hash publicado por el DMS")
            return data, meta.mime_type, meta.title, meta.version, True
        if document.snapshot_deleted_at is not None:
            raise LinkUnavailableError()
        data = self.storage.get(document.snapshot_key)
        if hashlib.sha256(data).hexdigest() != document.sha256:
            raise UpstreamError("La copia compartida no supera la verificación de integridad")
        return data, document.mime_type, document.title, document.source_version, False

    # ------------------------------------------------------------------ inicio de sesión
    def info(self, token: str, ctx: RequestContext) -> AccessInfo:
        share = self._load_usable(token, ctx)
        audience = Audience(share.audience)
        self._audit(share, AuditEventType.LINK_OPENED, ctx)
        return AccessInfo(
            shared_by=share.sharer.name,
            audience=audience,
            permission=Permission(share.permission),
            requires_code=audience is Audience.SPECIFIC,
            destination=(
                notifications.masked_destination(share) if audience is Audience.SPECIFIC else None
            ),
            # A una persona no verificada no se le revela el título (un enlace reenviado no filtra).
            document_title=share.document.title if audience is Audience.ANYONE else None,
            expires_at=share.expires_at,
        )

    def request_otp(self, token: str, ctx: RequestContext) -> OtpIssued:
        share = self._load_usable(token, ctx)
        if Audience(share.audience) is not Audience.SPECIFIC:
            raise ConflictError("Este enlace no requiere código")
        sent = self.db.scalar(
            select(func.count(OtpChallenge.id)).where(OtpChallenge.share_id == share.id)
        )
        if (sent or 0) >= self.settings.otp_max_sends:
            raise TooManyRequestsError("Se alcanzó el máximo de códigos para este enlace")

        now = datetime.now(UTC)
        self.db.execute(  # un único código vigente: los anteriores se invalidan
            update(OtpChallenge)
            .where(OtpChallenge.share_id == share.id, OtpChallenge.consumed_at.is_(None))
            .values(consumed_at=now)
        )
        code = generate_otp()
        ttl = timedelta(minutes=self.settings.otp_ttl_minutes)
        self.db.add(
            OtpChallenge(
                share_id=share.id,
                code_hmac=otp_mac(code, share.id, self.settings.otp_secret.get_secret_value()),
                expires_at=now + ttl,
            )
        )
        message = messages.access_code(code=code, ttl_minutes=self.settings.otp_ttl_minutes)
        notifications.send(
            self.db,
            self.channels,
            share,
            kind=NotificationKind.OTP,
            subject=message.subject,
            body=message.body,
            actor_type=ActorType.SYSTEM,
            actor_id=None,
            ctx=ctx,
            settings=self.settings,
        )
        self._audit(share, AuditEventType.OTP_SENT, ctx)
        return OtpIssued(
            sent_to=notifications.masked_destination(share),
            expires_in_seconds=int(ttl.total_seconds()),
        )

    def verify(self, token: str, code: str, ctx: RequestContext) -> AccessSession:
        share = self._load_usable(token, ctx)
        if Audience(share.audience) is not Audience.SPECIFIC:
            raise ConflictError("Este enlace no requiere código")
        now = datetime.now(UTC)
        challenge = self.db.scalar(
            select(OtpChallenge)
            .where(OtpChallenge.share_id == share.id, OtpChallenge.consumed_at.is_(None))
            .order_by(OtpChallenge.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        if challenge is None or challenge.expires_at <= now:
            self._audit(share, AuditEventType.OTP_FAILED, ctx, reason="NO_ACTIVE_CODE")
            self.db.commit()
            raise InvalidOtpError("Solicite un nuevo código")

        secret = self.settings.otp_secret.get_secret_value()
        if not verify_otp(code, share.id, secret, challenge.code_hmac):
            challenge.attempts += 1
            remaining = self.settings.otp_max_attempts - challenge.attempts
            self._audit(
                share,
                AuditEventType.OTP_FAILED,
                ctx,
                reason="WRONG_CODE",
                attempts=challenge.attempts,
            )
            if remaining <= 0:
                challenge.consumed_at = now
                share.status = ShareStatus.LOCKED.value
                self._audit(
                    share,
                    AuditEventType.SHARE_LOCKED,
                    ctx,
                    ActorType.SYSTEM,
                    reason="OTP_MAX_ATTEMPTS",
                )
                self.db.commit()
                raise LinkUnavailableError()
            self.db.commit()
            raise InvalidOtpError(remaining_attempts=remaining)

        challenge.consumed_at = now
        self._audit(share, AuditEventType.OTP_VERIFIED, ctx)
        return self._consume_access(share, ctx)

    def open(self, token: str, ctx: RequestContext) -> AccessSession:
        """Cualquiera con el enlace: inicia sesión sin código."""
        share = self._load_usable(token, ctx)
        if Audience(share.audience) is not Audience.ANYONE:
            raise ConflictError("Este enlace requiere verificación con código")
        session = self._consume_access(share, ctx)
        self._audit(share, AuditEventType.ACCESS_GRANTED, ctx, audience=share.audience)
        return session

    # ------------------------------------------------------------------ uso del documento
    def document(self, token: str, access_token: str, ctx: RequestContext) -> DocumentView:
        share = self._session(token, access_token, ctx)
        data, mime, title, version, live = self._content(share)
        permission = Permission(share.permission)
        self._audit(
            share,
            AuditEventType.DOCUMENT_VIEWED,
            ctx,
            version=version,
            permission=permission.value,
            live=live,
        )
        return DocumentView(
            title=title,
            mime_type=mime,
            kind=render.kind(mime),
            version=version,
            live=live,
            page_count=render.page_count(data, mime),
            permission=permission,
            can_download=permission in (Permission.DOWNLOAD, Permission.EDIT),
            can_edit=permission is Permission.EDIT,
            viewer_label=self._viewer_label(share),
        )

    def page(self, token: str, access_token: str, number: int, ctx: RequestContext) -> bytes:
        share = self._session(token, access_token, ctx)
        data, mime, _, _, _ = self._content(share)
        stamp = self._stamp(share, "Vista protegida ·")
        try:
            return render.render_page(data, mime, number - 1, stamp)
        except (IndexError, render.UnsupportedPreview) as exc:
            raise ValidationFailedError(str(exc)) from exc

    def text(self, token: str, access_token: str, ctx: RequestContext) -> str:
        share = self._session(token, access_token, ctx)
        data, mime, _, _, _ = self._content(share)
        if render.kind(mime) != "text":
            raise ValidationFailedError("El documento no es de texto")
        return data.decode("utf-8", errors="replace")

    def download(self, token: str, access_token: str, ctx: RequestContext) -> Payload:
        share = self._session(token, access_token, ctx)
        if Permission(share.permission) is Permission.VIEW:
            self._audit(share, AuditEventType.ACCESS_DENIED, ctx, reason="DOWNLOAD_NOT_ALLOWED")
            self.db.commit()
            raise ForbiddenError("Este enlace es de solo lectura: la descarga no está permitida")
        data, mime, title, version, live = self._content(share)
        payload, watermarked = apply_watermark(data, mime, self._stamp(share, "Compartido con"))
        self._audit(
            share,
            AuditEventType.DOCUMENT_ACCESSED,
            ctx,
            mode="download",
            version=version,
            live=live,
            watermarked=watermarked,
            sha256=hashlib.sha256(data).hexdigest(),
        )
        ext = {"application/pdf": "pdf", "image/png": "png", "image/jpeg": "jpg"}.get(mime, "bin")
        return Payload(payload, _safe_filename(title, ext), mime)

    def upload_version(
        self, token: str, access_token: str, file: UploadedFile, comment: str, ctx: RequestContext
    ) -> VersionPublished:
        share = self._session(token, access_token, ctx)
        if Permission(share.permission) is not Permission.EDIT:
            self._audit(share, AuditEventType.ACCESS_DENIED, ctx, reason="EDIT_NOT_ALLOWED")
            self.db.commit()
            raise ForbiddenError("Este enlace no permite editar el documento")
        recipient = share.recipient
        actor = (
            f"destinatario:{recipient.email or recipient.phone}" if recipient else "destinatario"
        )
        document = self.source.upload_version(
            share.document.source_id, file=file, comment=comment, actor=actor
        )
        text = extract_text(file.data, document.mime_type)
        findings = summarize(detect(text)) if text else []
        self._audit(
            share,
            AuditEventType.DOCUMENT_VERSION_UPLOADED,
            ctx,
            source_document_id=document.id,
            version=document.version,
            sha256=document.sha256,
            comment=comment,
            findings={f.type: f.count for f in findings},
        )
        return VersionPublished(version=document.version, findings=findings)
