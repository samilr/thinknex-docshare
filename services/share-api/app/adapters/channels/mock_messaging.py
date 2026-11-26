import logging
import uuid

from app.adapters.channels.base import DeliveryResult, OutboundMessage
from app.core.security import mask_phone

logger = logging.getLogger(__name__)


class MockMessagingChannel:
    """Integración simulada de WhatsApp / SMS.

    En producción se reemplaza por WhatsApp Business Cloud API (plantillas aprobadas) o un
    proveedor SMS; la interfaz no cambia. Aquí solo se registra el envío.
    """

    def __init__(self, provider: str) -> None:
        self._provider = provider

    def send(self, message: OutboundMessage) -> DeliveryResult:
        message_id = f"{self._provider}-{uuid.uuid4().hex[:12]}"
        logger.info(
            "mensaje simulado enviado",
            extra={
                "extra_fields": {
                    "provider": self._provider,
                    "to": mask_phone(message.to),
                    "kind": message.kind.value,
                    "provider_message_id": message_id,
                }
            },
        )
        return DeliveryResult(ok=True, provider_message_id=message_id)
