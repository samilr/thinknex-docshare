import logging

import httpx

from app.adapters.channels.base import DeliveryResult, OutboundMessage

logger = logging.getLogger(__name__)
RESEND_URL = "https://api.resend.com/emails"


class ResendEmailChannel:
    """Email real vía la API HTTP de Resend (EMAIL_PROVIDER=resend + RESEND_API_KEY).

    El remitente (EMAIL_FROM) debe pertenecer a un dominio verificado en Resend; con el
    remitente de pruebas de Resend solo se puede enviar al correo dueño de la cuenta.
    """

    def __init__(self, api_key: str, sender: str, timeout: float = 10.0) -> None:
        self._client = httpx.Client(timeout=timeout, headers={"Authorization": f"Bearer {api_key}"})
        self._sender = sender

    def send(self, message: OutboundMessage) -> DeliveryResult:
        try:
            response = self._client.post(
                RESEND_URL,
                json={
                    "from": self._sender,
                    "to": [message.to],
                    "subject": message.subject,
                    "text": message.body,
                },
            )
        except httpx.HTTPError as exc:
            logger.warning("fallo envío Resend", extra={"extra_fields": {"error": str(exc)}})
            return DeliveryResult(ok=False, error=type(exc).__name__)
        if response.is_error:
            logger.warning(
                "Resend rechazó el envío", extra={"extra_fields": {"status": response.status_code}}
            )
            return DeliveryResult(ok=False, error=f"HTTP {response.status_code}")
        return DeliveryResult(ok=True, provider_message_id=response.json().get("id"))
