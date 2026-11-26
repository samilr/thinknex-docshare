"""Flujo del destinatario: abrir enlace -> pedir OTP -> verificar -> descargar con marca de agua.

Toda denegación se audita con su causa real, pero hacia afuera la respuesta es uniforme
(``LinkUnavailableError``) para no revelar si un enlace existe ni por qué dejó de servir.
"""

import hashlib
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.adapters.channels.base import ChannelRegistry
from app.adapters.storage import BlobStorage
from app.adapters.watermark import apply_watermark
from app.core.config import Settings
from app.core.errors import InvalidOtpError, LinkUnavailableError, TooManyRequestsError
from app.core.security import (
    InvalidTokenError,
    create_download_token,
    decode_download_token,
    generate_otp,
    hash_token,
    otp_mac,
    verify_otp,
)
from app.db.models import OtpChallenge, Share
from app.domain.enums import ActorType, AuditEventType, NotificationKind, ShareStatus
from app.services import audit_service, notifications
from app.services.context import RequestContext


@dataclass(frozen=True)
class LandingInfo:
    shared_by: str
    otp_destination: str
    channel: str
    expires_at: datetime


@dataclass(frozen=True)
class OtpIssued:
    sent_to: str
    expires_in_seconds: int


@dataclass(frozen=True)
class DownloadGrant:
    access_token: str
    expires_in: int
    remaining_accesses: int


@dataclass(frozen=True)
class DownloadPayload:
    content: bytes
    filename: str
    mime_type: str


@dataclass
class AccessService:
    db: Session
    settings: Settings
    storage: BlobStorage
    channels: ChannelRegistry

    # ---------------------------------------------------------------- helpers
    def _recipient_actor(self, share: Share) -> str:
        return str(share.recipient_id)

    def _deny(self, share: Share | None, ctx: RequestContext, reason: str) -> LinkUnavailableError:
        audit_service.record(
            self.db,
            event_type=AuditEventType.ACCESS_DENIED,
            actor_type=ActorType.RECIPIENT,
            actor_id=self._recipient_actor(share) if share else None,
            share_id=share.id if share else None,
            document_id=share.document_id if share else None,
            channel=share.channel if share else None,
            ctx=ctx,
            details={"reason": reason},
        )
        self.db.commit()  # la denegación debe persistir aunque la request termine en error
        return LinkUnavailableError()

    def _load_usable(self, token: str, ctx: RequestContext) -> Share:
        share = self.db.scalar(select(Share).where(Share.token_hash == hash_token(token)))
        if share is None:
            raise self._deny(None, ctx, "UNKNOWN_TOKEN")
        if share.status == ShareStatus.ACTIVE.value and share.expires_at <= datetime.now(UTC):
            share.status = ShareStatus.EXPIRED.value
            audit_service.record(
                self.db,
                event_type=AuditEventType.SHARE_EXPIRED,
                actor_type=ActorType.SYSTEM,
                share_id=share.id,
                document_id=share.document_id,
                channel=share.channel,
            )
        if share.status != ShareStatus.ACTIVE.value:
            raise self._deny(share, ctx, share.status)
        return share

    def _lock(self, share: Share, ctx: RequestContext) -> None:
        share.status = ShareStatus.LOCKED.value
        audit_service.record(
            self.db,
            event_type=AuditEventType.SHARE_LOCKED,
            actor_type=ActorType.SYSTEM,
            share_id=share.id,
            document_id=share.document_id,
            channel=share.channel,
            ctx=ctx,
            details={"reason": "OTP_MAX_ATTEMPTS"},
        )

    # ---------------------------------------------------------------- casos de uso
    def open_link(self, token: str, ctx: RequestContext) -> LandingInfo:
        share = self._load_usable(token, ctx)
        audit_service.record(
            self.db,
            event_type=AuditEventType.LINK_OPENED,
            actor_type=ActorType.RECIPIENT,
            actor_id=self._recipient_actor(share),
            share_id=share.id,
            document_id=share.document_id,
            channel=share.channel,
            ctx=ctx,
        )
        # No se revela el título del documento antes del OTP: un enlace reenviado no filtra nada.
        return LandingInfo(
            shared_by=share.sharer.name,
            otp_destination=notifications.masked_destination(share),
            channel=share.channel,
            expires_at=share.expires_at,
        )

    def request_otp(self, token: str, ctx: RequestContext) -> OtpIssued:
        share = self._load_usable(token, ctx)
        sent = self.db.scalar(
            select(func.count(OtpChallenge.id)).where(OtpChallenge.share_id == share.id)
        )
        if (sent or 0) >= self.settings.otp_max_sends:
            raise TooManyRequestsError("Se alcanzó el máximo de códigos para este enlace")

        now = datetime.now(UTC)
        # Un único código vigente: los anteriores se invalidan.
        self.db.execute(
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
        notifications.send(
            self.db,
            self.channels,
            share,
            kind=NotificationKind.OTP,
            subject="Tu código de acceso",
            body=(
                f"Tu código para acceder al documento es {code}. "
                f"Vence en {self.settings.otp_ttl_minutes} minutos. No lo compartas."
            ),
            actor_type=ActorType.SYSTEM,
            actor_id=None,
            ctx=ctx,
        )
        audit_service.record(
            self.db,
            event_type=AuditEventType.OTP_SENT,
            actor_type=ActorType.RECIPIENT,
            actor_id=self._recipient_actor(share),
            share_id=share.id,
            document_id=share.document_id,
            channel=share.channel,
            ctx=ctx,
        )
        return OtpIssued(
            sent_to=notifications.masked_destination(share),
            expires_in_seconds=int(ttl.total_seconds()),
        )

    def verify(self, token: str, code: str, ctx: RequestContext) -> DownloadGrant:
        share = self._load_usable(token, ctx)
        now = datetime.now(UTC)
        challenge = self.db.scalar(
            select(OtpChallenge)
            .where(OtpChallenge.share_id == share.id, OtpChallenge.consumed_at.is_(None))
            .order_by(OtpChallenge.created_at.desc())
            .limit(1)
            .with_for_update()
        )
        secret = self.settings.otp_secret.get_secret_value()
        if challenge is None or challenge.expires_at <= now:
            self._otp_failed(share, ctx, "NO_ACTIVE_CODE")
            self.db.commit()
            raise InvalidOtpError("Solicite un nuevo código")

        if not verify_otp(code, share.id, secret, challenge.code_hmac):
            challenge.attempts += 1
            remaining = self.settings.otp_max_attempts - challenge.attempts
            self._otp_failed(share, ctx, "WRONG_CODE", attempts=challenge.attempts)
            if remaining <= 0:
                challenge.consumed_at = now
                self._lock(share, ctx)
                self.db.commit()
                raise LinkUnavailableError()
            self.db.commit()
            raise InvalidOtpError(remaining_attempts=remaining)

        challenge.consumed_at = now
        audit_service.record(
            self.db,
            event_type=AuditEventType.OTP_VERIFIED,
            actor_type=ActorType.RECIPIENT,
            actor_id=self._recipient_actor(share),
            share_id=share.id,
            document_id=share.document_id,
            channel=share.channel,
            ctx=ctx,
        )
        ttl = self.settings.access_token_ttl_minutes
        return DownloadGrant(
            access_token=create_download_token(
                share.id, self.settings.jwt_secret.get_secret_value(), ttl
            ),
            expires_in=ttl * 60,
            remaining_accesses=share.max_accesses - share.access_count,
        )

    def _otp_failed(self, share: Share, ctx: RequestContext, reason: str, **extra: int) -> None:
        audit_service.record(
            self.db,
            event_type=AuditEventType.OTP_FAILED,
            actor_type=ActorType.RECIPIENT,
            actor_id=self._recipient_actor(share),
            share_id=share.id,
            document_id=share.document_id,
            channel=share.channel,
            ctx=ctx,
            details={"reason": reason, **extra},
        )

    def download(self, token: str, access_token: str, ctx: RequestContext) -> DownloadPayload:
        share = self._load_usable(token, ctx)
        try:
            claims = decode_download_token(
                access_token, self.settings.jwt_secret.get_secret_value()
            )
        except InvalidTokenError:
            raise self._deny(share, ctx, "INVALID_ACCESS_TOKEN") from None
        if claims["sub"] != str(share.id):
            raise self._deny(share, ctx, "ACCESS_TOKEN_SHARE_MISMATCH")

        document = share.document
        if document.snapshot_deleted_at is not None:
            raise self._deny(share, ctx, "SNAPSHOT_PURGED")
        content = self.storage.get(document.snapshot_key)
        if hashlib.sha256(content).hexdigest() != document.sha256:
            raise self._deny(share, ctx, "SNAPSHOT_INTEGRITY_FAILURE")

        # Consumo atómico: dos descargas concurrentes nunca superan max_accesses.
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

        stamp = (
            f"Compartido con {share.recipient.name} · {datetime.now(UTC):%Y-%m-%d %H:%M} UTC · "
            f"ref {str(share.id)[:8]}"
        )
        payload, watermarked = apply_watermark(content, document.mime_type, stamp)
        audit_service.record(
            self.db,
            event_type=AuditEventType.DOCUMENT_ACCESSED,
            actor_type=ActorType.RECIPIENT,
            actor_id=self._recipient_actor(share),
            share_id=share.id,
            document_id=share.document_id,
            channel=share.channel,
            ctx=ctx,
            details={
                "access_number": new_count,
                "max_accesses": share.max_accesses,
                "sha256": document.sha256,
                "watermarked": watermarked,
                "access_jti": claims.get("jti"),
            },
        )
        ascii_title = unicodedata.normalize("NFKD", document.title).encode("ascii", "ignore")
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in ascii_title.decode())[
            :80
        ]
        return DownloadPayload(
            content=payload, filename=f"{safe_name}.pdf", mime_type=document.mime_type
        )
