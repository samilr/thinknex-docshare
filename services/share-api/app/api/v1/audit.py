import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AuditorDep, DbDep
from app.domain.enums import AuditEventType, Channel
from app.schemas import AuditEventOut, AuditPage, ChainVerificationOut
from app.services import audit_service

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditPage, response_model_by_alias=True)
def list_events(
    _: AuditorDep,
    db: DbDep,
    document_id: Annotated[str | None, Query(description="ID del DMS, p. ej. doc-002")] = None,
    share_id: uuid.UUID | None = None,
    actor_id: str | None = None,
    channel: Channel | None = None,
    event_type: AuditEventType | None = None,
    occurred_from: Annotated[datetime | None, Query(alias="from")] = None,
    occurred_to: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditPage:
    """Quién hizo qué, cuándo y por qué medio. Más reciente primero."""
    rows, total = audit_service.query(
        db,
        audit_service.AuditFilters(
            source_document_id=document_id,
            share_id=share_id,
            actor_id=actor_id,
            channel=channel,
            event_type=event_type,
            occurred_from=occurred_from,
            occurred_to=occurred_to,
        ),
        limit=limit,
        offset=offset,
    )
    labels = audit_service.actor_labels(db, rows)
    items = [
        AuditEventOut.model_validate(r).model_copy(update={"actor": labels.get(r.actor_id or "")})
        for r in rows
    ]
    return AuditPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/verify", response_model=ChainVerificationOut)
def verify_chain(_: AuditorDep, db: DbDep) -> ChainVerificationOut:
    """Recalcula la cadena de hashes completa y reporta el primer eslabón alterado, si existe."""
    result = audit_service.verify_chain(db)
    return ChainVerificationOut(**result.__dict__)
