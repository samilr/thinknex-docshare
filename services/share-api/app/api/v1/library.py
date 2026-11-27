"""Biblioteca de documentos (estilo SharePoint): navegar, subir, versionar, ver y compartir."""

from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field

from app.adapters.document_source import SourceFolder, SourceLibrary, UploadedFile
from app.api.deps import ContextDep, DbDep, LibraryServiceDep, LibraryUserDep, SettingsDep
from app.api.v1.audit import events_out
from app.core.config import Settings
from app.domain.enums import Classification
from app.schemas import AuditEventOut, ShareOut
from app.services.library_service import (
    DocumentDetail,
    LibraryDocument,
    LibraryItems,
    UploadResult,
)

router = APIRouter(prefix="/library", tags=["library"])


class FolderCreate(BaseModel):
    library_id: str
    parent_id: str | None = None
    name: str = Field(min_length=1, max_length=200)


async def _read(file: UploadFile, settings: Settings) -> UploadedFile:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"El archivo supera el máximo de {settings.max_upload_mb} MB",
        )
    return UploadedFile(
        filename=file.filename or "archivo",
        content_type=file.content_type or "application/octet-stream",
        data=data,
    )


@router.get("/libraries", response_model=list[SourceLibrary])
def libraries(_: LibraryUserDep, service: LibraryServiceDep) -> list[SourceLibrary]:
    return service.libraries()


@router.get("/items", response_model=LibraryItems)
def items(
    _: LibraryUserDep,
    service: LibraryServiceDep,
    library_id: str,
    folder_id: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> LibraryItems:
    """Contenido de una ubicación: migas de pan, carpetas y archivos (con accesos activos)."""
    return service.items(library_id, folder_id, q or None)


@router.post("/folders", response_model=SourceFolder, status_code=status.HTTP_201_CREATED)
def create_folder(
    body: FolderCreate, user: LibraryUserDep, service: LibraryServiceDep, ctx: ContextDep
) -> SourceFolder:
    return service.create_folder(user, body.library_id, body.parent_id, body.name, ctx)


@router.post(
    "/documents",
    response_model=UploadResult,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "name_conflict: ya existe; subir como nueva versión"}},
)
async def upload(
    user: LibraryUserDep,
    service: LibraryServiceDep,
    settings: SettingsDep,
    ctx: ContextDep,
    file: Annotated[UploadFile, File()],
    library_id: Annotated[str, Form()],
    classification: Annotated[Classification, Form()],
    folder_id: Annotated[str | None, Form()] = None,
    title: Annotated[str | None, Form(max_length=300)] = None,
) -> UploadResult:
    """Sube un archivo. Devuelve los datos personales detectados para advertir en la interfaz."""
    return service.upload(
        user,
        await _read(file, settings),
        library_id=library_id,
        folder_id=folder_id or None,
        classification=classification,
        title=title or None,
        ctx=ctx,
    )


@router.post(
    "/documents/{doc_id}/versions", response_model=UploadResult, status_code=status.HTTP_201_CREATED
)
async def upload_version(
    doc_id: str,
    user: LibraryUserDep,
    service: LibraryServiceDep,
    settings: SettingsDep,
    ctx: ContextDep,
    file: Annotated[UploadFile, File()],
    comment: Annotated[str, Form(max_length=500)] = "",
) -> UploadResult:
    return service.upload_version(user, doc_id, await _read(file, settings), comment, ctx)


class DocumentUpdate(BaseModel):
    name: str | None = Field(
        default=None, min_length=1, max_length=150, description="Nuevo nombre, sin extensión"
    )
    classification: Classification | None = Field(
        default=None, description="Solo ADMIN: cambia qué reglas de la política aplican"
    )


class DeletedOut(BaseModel):
    revoked_shares: int


@router.patch(
    "/documents/{doc_id}",
    response_model=LibraryDocument,
    responses={409: {"description": "name_conflict: ya existe ese nombre en la carpeta"}},
)
def update(
    doc_id: str,
    body: DocumentUpdate,
    user: LibraryUserDep,
    service: LibraryServiceDep,
    ctx: ContextDep,
) -> LibraryDocument:
    """Renombra y/o reclasifica. Queda en la auditoría con el valor anterior y el nuevo."""
    return service.update(user, doc_id, name=body.name, classification=body.classification, ctx=ctx)


@router.delete("/documents/{doc_id}", response_model=DeletedOut)
def delete(
    doc_id: str, user: LibraryUserDep, service: LibraryServiceDep, ctx: ContextDep
) -> DeletedOut:
    """Elimina el archivo (ADMIN o quien lo subió) y revoca sus envíos activos."""
    return DeletedOut(revoked_shares=service.delete(user, doc_id, ctx))


@router.get("/documents/{doc_id}", response_model=DocumentDetail)
def detail(doc_id: str, _: LibraryUserDep, service: LibraryServiceDep) -> DocumentDetail:
    return service.detail(doc_id)


@router.get("/documents/{doc_id}/content", response_class=Response)
def content(
    doc_id: str,
    user: LibraryUserDep,
    service: LibraryServiceDep,
    ctx: ContextDep,
    version: Annotated[int | None, Query(ge=1)] = None,
    disposition: Literal["inline", "attachment"] = "inline",
) -> Response:
    """Vista o descarga interna: PDF con marca de agua del usuario y evento DOCUMENT_VIEWED."""
    payload = service.content(user, doc_id, version=version, disposition=disposition, ctx=ctx)
    ascii_name = payload.filename.encode("ascii", "ignore").decode() or "documento"
    return Response(
        content=payload.content,
        media_type=payload.mime_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{ascii_name}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/documents/{doc_id}/access", response_model=list[ShareOut])
def access(doc_id: str, _: LibraryUserDep, service: LibraryServiceDep) -> list[ShareOut]:
    """Personas con acceso: envíos del archivo (vigentes primero)."""
    return service.access(doc_id)


@router.get(
    "/documents/{doc_id}/activity",
    response_model=list[AuditEventOut],
    response_model_by_alias=True,
)
def activity(
    doc_id: str, _: LibraryUserDep, service: LibraryServiceDep, db: DbDep
) -> list[AuditEventOut]:
    return events_out(db, service.activity(doc_id))
