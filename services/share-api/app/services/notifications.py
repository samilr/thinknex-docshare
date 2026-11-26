"""Envío de notificaciones al destinatario por el canal elegido, con registro y auditoría."""

from sqlalchemy.orm import Session

from app.adapters.channels.base import ChannelRegistry, DeliveryResult, OutboundMessage
from app.core.errors import ValidationFailedError
from app.core.security import mask_email, mask_phone
from app.db.models import Notification, Share
from app.domain.enums import (
    ActorType,
    AuditEventType,
    Channel,
    NotificationKind,
    NotificationStatus,
)
from app.services import audit_service
from app.services.context import RequestContext


def destination(share: Share) -> str:
    recipient = share.recipient
    to = recipient.email if Channel(share.channel) is Channel.EMAIL else recipient.phone
    if not to:  # la validación de entrada lo impide; defensa en profundidad
        raise ValidationFailedError("El destinatario no tiene contacto para el canal elegido")
    return to


def masked_destination(share: Share) -> str:
    to = destination(share)
    return mask_email(to) if Channel(share.channel) is Channel.EMAIL else mask_phone(to)


def send(
    db: Session,
    channels: ChannelRegistry,
    share: Share,
    *,
    kind: NotificationKind,
    subject: str,
    body: str,
    actor_type: ActorType,
    actor_id: str | None,
    ctx: RequestContext | None,
) -> DeliveryResult:
    channel = Channel(share.channel)
    result = channels.get(channel).send(
        OutboundMessage(
            channel=channel, to=destination(share), subject=subject, body=body, kind=kind
        )
    )
    db.add(
        Notification(
            share_id=share.id,
            channel=channel.value,
            destination_masked=masked_destination(share),
            kind=kind.value,
            status=(NotificationStatus.SENT if result.ok else NotificationStatus.FAILED).value,
            provider_message_id=result.provider_message_id,
            error=result.error,
        )
    )
    if kind is NotificationKind.LINK:
        audit_service.record(
            db,
            event_type=(
                AuditEventType.NOTIFICATION_SENT
                if result.ok
                else AuditEventType.NOTIFICATION_FAILED
            ),
            actor_type=actor_type,
            actor_id=actor_id,
            share_id=share.id,
            document_id=share.document_id,
            channel=channel,
            ctx=ctx,
            details={
                "destination": masked_destination(share),
                "provider_message_id": result.provider_message_id,
                "error": result.error,
            },
        )
    return result
