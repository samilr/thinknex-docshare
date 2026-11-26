import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.api.deps import ContextDep, SharerDep, ShareServiceDep
from app.schemas import PrecheckRequest, PrecheckResponse, ShareOut, ShareRequest

router = APIRouter(prefix="/shares", tags=["shares"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"description": "Bloqueado por política (p. ej. RESTRICTED a externo)"},
    409: {"description": "Contenido sensible: reenviar con acknowledge_sensitive=true"},
    502: {"description": "Sistema documental no disponible o integridad fallida"},
}


@router.post("/precheck", response_model=PrecheckResponse, responses=_ERRORS)
def precheck(body: PrecheckRequest, user: SharerDep, service: ShareServiceDep) -> PrecheckResponse:
    """Evalúa la sensibilidad sin compartir: permite a la interfaz advertir antes de enviar."""
    return service.precheck(user, body.document_id, body.recipient)


@router.post("", response_model=ShareOut, status_code=status.HTTP_201_CREATED, responses=_ERRORS)
def create_share(
    body: ShareRequest, user: SharerDep, service: ShareServiceDep, ctx: ContextDep
) -> ShareOut:
    """Comparte un documento. El enlace se envía SOLO al destinatario; nunca se devuelve aquí."""
    return service.create(user, body, ctx)


@router.get("", response_model=list[ShareOut])
def list_shares(
    user: SharerDep,
    service: ShareServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ShareOut]:
    return service.list_own(user, limit=limit, offset=offset)


@router.get("/{share_id}", response_model=ShareOut)
def get_share(share_id: uuid.UUID, user: SharerDep, service: ShareServiceDep) -> ShareOut:
    return service.get_own(user, share_id)


@router.post("/{share_id}/revoke", response_model=ShareOut)
def revoke_share(
    share_id: uuid.UUID, user: SharerDep, service: ShareServiceDep, ctx: ContextDep
) -> ShareOut:
    return service.revoke(user, share_id, ctx)
