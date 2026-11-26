from dataclasses import dataclass


@dataclass(frozen=True)
class RequestContext:
    """Datos del canal de la solicitud que se registran en la auditoría."""

    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None
