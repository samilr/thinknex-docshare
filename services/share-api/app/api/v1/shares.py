import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, status

from app.api.deps import (
    AnyRoleDep,
    ContextDep,
    DbDep,
    RevokerDep,
    SharerDep,
    ShareServiceDep,
)
from app.api.v1.audit import events_out
from app.domain.enums import Channel, ShareStatus
from app.schemas import (
    AuditEventOut,
    PrecheckRequest,
    PrecheckResponse,
    ShareListPage,
    ShareOut,
    ShareRequest,
)
from app.services.share_service import ShareScope

router = APIRouter(prefix="/shares", tags=["shares"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"description": "Bloqueado por política (p. ej. RESTRICTED a externo)"},
    409: {"description": "Contenido sensible: reenviar con acknowledge_sensitive=true"},
    502: {"description": "Sistema documental no disponible o integridad fallida"},
}


@router.post("/precheck", response_model=PrecheckResponse, responses=_ERRORS)
def precheck(body: PrecheckRequest, user: SharerDep, service: ShareServiceDep) -> PrecheckResponse:
    """Evalúa la sensibilidad sin compartir: permite a la interfaz advertir antes de enviar."""
    return service.precheck(user, body.document_id, body.recipient, body.audience)


@router.post("", response_model=ShareOut, status_code=status.HTTP_201_CREATED, responses=_ERRORS)
def create_share(
    body: ShareRequest, user: SharerDep, service: ShareServiceDep, ctx: ContextDep
) -> ShareOut:
    """Comparte un documento. El enlace se envía SOLO al destinatario; nunca se devuelve aquí."""
    return service.create(user, body, ctx)


@router.get("", response_model=ShareListPage)
def list_shares(
    user: AnyRoleDep,
    service: ShareServiceDep,
    scope: Annotated[ShareScope, Query(description="mine | all (all: ADMIN/AUDITOR)")] = "mine",
    status_filter: Annotated[ShareStatus | None, Query(alias="status")] = None,
    channel: Channel | None = None,
    document_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ShareListPage:
    return service.search(
        user,
        scope=scope,
        status=status_filter,
        channel=channel,
        document_id=document_id,
        limit=limit,
        offset=offset,
    )


@router.get("/{share_id}", response_model=ShareOut)
def get_share(share_id: uuid.UUID, user: AnyRoleDep, service: ShareServiceDep) -> ShareOut:
    return service.get(user, share_id)


@router.get(
    "/{share_id}/timeline", response_model=list[AuditEventOut], response_model_by_alias=True
)
def share_timeline(
    share_id: uuid.UUID, user: AnyRoleDep, service: ShareServiceDep, db: DbDep
) -> list[AuditEventOut]:
    """Eventos de auditoría del share en orden cronológico (detalle en el portal)."""
    return events_out(db, service.timeline(user, share_id))


@router.post("/{share_id}/revoke", response_model=ShareOut)
def revoke_share(
    share_id: uuid.UUID, user: RevokerDep, service: ShareServiceDep, ctx: ContextDep
) -> ShareOut:
    return service.revoke(user, share_id, ctx)


@router.post("/{share_id}/link", response_model=ShareOut)
def rotate_link(
    share_id: uuid.UUID, user: RevokerDep, service: ShareServiceDep, ctx: ContextDep
) -> ShareOut:
    """Genera un enlace nuevo (canal LINK). El anterior deja de funcionar de inmediato."""
    return service.rotate_link(user, share_id, ctx)
