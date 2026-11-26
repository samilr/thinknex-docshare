"""Puerto de canales de notificación.

Agregar un canal nuevo (Teams, Slack, etc.) = implementar ``ChannelAdapter`` y registrarlo.
El documento nunca viaja por el canal: solo el enlace o el código OTP.
"""

from dataclasses import dataclass
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


class ChannelRegistry:
    def __init__(self, adapters: dict[Channel, ChannelAdapter]) -> None:
        self._adapters = adapters

    def get(self, channel: Channel) -> ChannelAdapter:
        return self._adapters[channel]
