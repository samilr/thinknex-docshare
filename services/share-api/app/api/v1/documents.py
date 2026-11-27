from typing import Annotated

from fastapi import APIRouter, Query

from app.adapters.document_source import SourcePage
from app.api.deps import ComponentsDep, SharingDep

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=SourcePage)
def list_documents(
    _: SharingDep,
    components: ComponentsDep,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SourcePage:
    """Catálogo del sistema documental (proxy), para elegir qué compartir."""
    return components.source.list(q=q, limit=limit, offset=offset)
