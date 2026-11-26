"""Puerto de canales de notificación.

Agregar un canal nuevo (Teams, Slack, etc.) = implementar ``ChannelAdapter`` y registrarlo.
El documento nunca viaja por el canal: solo el enlace o el código OTP.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from app.domain.enums import Channel, NotificationKind


@dataclass(frozen=True)
class OutboundMessage:
    channel: Channel
    to: str
    subject: str
    body: str
    kind: NotificationKind


@dataclass(frozen=True)
class DeliveryResult:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None


class ChannelAdapter(Protocol):
    def send(self, message: OutboundMessage) -> DeliveryResult: ...


@dataclass
class DevOutbox:
    """Bandeja en memoria SOLO para ENV=dev: permite a la demo leer enlaces y OTP simulados."""

    messages: deque[dict[str, str]] = field(default_factory=lambda: deque(maxlen=200))

    def record(self, message: OutboundMessage) -> None:
        self.messages.append(
            {
                "at": datetime.now(UTC).isoformat(),
                "channel": message.channel.value,
                "kind": message.kind.value,
                "to": message.to,
                "subject": message.subject,
                "body": message.body,
            }
        )


class RecordingChannel:
    """Decorador que copia cada mensaje a la DevOutbox antes de entregarlo."""

    def __init__(self, inner: ChannelAdapter, outbox: DevOutbox) -> None:
        self._inner = inner
        self._outbox = outbox

    def send(self, message: OutboundMessage) -> DeliveryResult:
        self._outbox.record(message)
        return self._inner.send(message)


class ChannelRegistry:
    def __init__(self, adapters: dict[Channel, ChannelAdapter]) -> None:
        self._adapters = adapters

    def get(self, channel: Channel) -> ChannelAdapter:
        return self._adapters[channel]
