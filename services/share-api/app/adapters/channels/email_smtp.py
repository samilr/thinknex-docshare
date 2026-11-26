import logging
import smtplib
import uuid
from email.message import EmailMessage

from app.adapters.channels.base import DeliveryResult, OutboundMessage

logger = logging.getLogger(__name__)


class SmtpEmailChannel:
    """Email real vía SMTP. En local apunta a Mailpit (bandeja web en http://localhost:8025)."""

    def __init__(self, host: str, port: int, sender: str) -> None:
        self._host = host
        self._port = port
        self._sender = sender

    def send(self, message: OutboundMessage) -> DeliveryResult:
        msg = EmailMessage()
        message_id = f"<{uuid.uuid4().hex}@demo-corp.example>"
        msg["From"] = self._sender
        msg["To"] = message.to
        msg["Subject"] = message.subject
        msg["Message-ID"] = message_id
        msg.set_content(message.body)
        try:
            with smtplib.SMTP(self._host, self._port, timeout=10) as smtp:
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            logger.warning("fallo envío email", extra={"extra_fields": {"error": str(exc)}})
            return DeliveryResult(ok=False, error=type(exc).__name__)
        return DeliveryResult(ok=True, provider_message_id=message_id)
