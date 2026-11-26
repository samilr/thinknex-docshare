from fastapi import APIRouter, HTTPException, status

from app.api.deps import ComponentsDep

router = APIRouter(prefix="/dev", tags=["dev (solo ENV=dev)"])


@router.get("/outbox")
def outbox(components: ComponentsDep, limit: int = 20) -> list[dict[str, str]]:
    """Mensajes simulados (WhatsApp/SMS/email) para la demo. No existe fuera de ENV=dev."""
    if components.outbox is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return list(reversed(components.outbox.messages))[:limit]
