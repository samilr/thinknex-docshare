"""Plantillas de los mensajes que recibe el destinatario (email, WhatsApp y SMS).

Marca del prototipo: "ThinkNex Docs". Es un ambiente de demostración con datos ficticios, por eso
todo mensaje lleva un aviso explícito para que nadie lo confunda con una comunicación oficial.
"""

from dataclasses import dataclass
from datetime import datetime

BRAND = "ThinkNex Docs"
DEMO_NOTICE = (
    "Mensaje de demostración del prototipo ThinkNex Docs (prueba técnica, datos ficticios). "
    "Si no lo esperabas, ignóralo."
)
SIGNATURE = f"Equipo {BRAND}"


@dataclass(frozen=True)
class Message:
    subject: str
    body: str


def share_link(
    *,
    recipient_name: str,
    sender_name: str,
    document_title: str,
    link: str,
    expires_at: datetime,
    max_accesses: int,
) -> Message:
    return Message(
        subject=f"{BRAND} · {sender_name} compartió un documento contigo",
        body=(
            f"Hola {recipient_name},\n\n"
            f'{sender_name} compartió contigo el documento "{document_title}" mediante {BRAND}.\n\n'
            f"Accede aquí: {link}\n\n"
            "Por seguridad te pediremos un código que enviaremos a este mismo medio. "
            f"El enlace vence el {expires_at:%Y-%m-%d %H:%M} UTC y permite "
            f"{max_accesses} descarga(s).\n\n"
            f"{SIGNATURE}\n\n{DEMO_NOTICE}\n"
        ),
    )


def access_code(*, code: str, ttl_minutes: int) -> Message:
    return Message(
        subject=f"{BRAND} · Tu código de acceso",
        body=(
            f"Tu código para acceder al documento es {code}. "
            f"Vence en {ttl_minutes} minutos. No lo compartas con nadie.\n\n"
            f"{SIGNATURE} · {DEMO_NOTICE}"
        ),
    )
