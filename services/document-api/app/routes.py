import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from app.catalog import Catalog, Classification, DocumentMeta, DocumentPage
from app.config import Settings


def _catalog(request: Request) -> Catalog:
    catalog: Catalog = request.app.state.catalog
    return catalog


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def require_api_key(
    settings: Annotated[Settings, Depends(_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.dms_api_key.get_secret_value()
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="API key inválida o ausente")


router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_api_key)])
CatalogDep = Annotated[Catalog, Depends(_catalog)]


def _get_or_404(catalog: Catalog, doc_id: str) -> DocumentMeta:
    doc = catalog.get(doc_id)
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Documento no encontrado")
    return doc


@router.get("", response_model=DocumentPage)
def list_documents(
    catalog: CatalogDep,
    q: str | None = None,
    classification: Classification | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentPage:
    return catalog.list(q=q, classification=classification, limit=limit, offset=offset)


@router.get("/{doc_id}", response_model=DocumentMeta)
def get_document(doc_id: str, catalog: CatalogDep) -> DocumentMeta:
    return _get_or_404(catalog, doc_id)


@router.get("/{doc_id}/content", response_class=Response)
def get_document_content(doc_id: str, catalog: CatalogDep) -> Response:
    doc = _get_or_404(catalog, doc_id)
    return Response(
        content=catalog.content(doc),
        media_type=doc.mime_type,
        headers={
            "ETag": f'"{doc.sha256}"',
            "X-Content-SHA256": doc.sha256,
            "X-Document-Version": str(doc.version),
            "Content-Disposition": f'attachment; filename="{doc.id}.pdf"',
        },
    )
