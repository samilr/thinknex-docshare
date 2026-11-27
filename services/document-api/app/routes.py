import secrets
from collections.abc import Iterator
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from app import repository as repo
from app.config import Settings
from app.db import session_scope
from app.schemas import (
    Classification,
    DocumentMeta,
    DocumentPage,
    DocumentRename,
    FolderCreate,
    FolderOut,
    LibraryOut,
    VersionOut,
)
from app.storage import BlobStore
from app.validation import InvalidUpload, validate_upload


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _store(request: Request) -> BlobStore:
    store: BlobStore = request.app.state.store
    return store


def _db(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    yield from session_scope(factory)


def require_api_key(
    settings: Annotated[Settings, Depends(_settings)],
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.dms_api_key.get_secret_value()
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="API key inválida o ausente")


def acting_user(x_acting_user: Annotated[str | None, Header()] = None) -> str:
    """Usuario final en nombre de quien actúa share-api (autoría de carpetas y versiones)."""
    return (x_acting_user or "sistema@thinknex.example")[:320]


router = APIRouter(dependencies=[Depends(require_api_key)])
DbDep = Annotated[Session, Depends(_db)]
StoreDep = Annotated[BlobStore, Depends(_store)]
ActorDep = Annotated[str, Depends(acting_user)]


def _extension(filename: str) -> str:
    return filename.rsplit(".", 1)[-1]


def _not_found(exc: repo.NotFound) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))


async def _read_upload(file: UploadFile, settings: Settings) -> tuple[str, str, str, bytes]:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    data = await file.read(max_bytes + 1)
    try:
        name, file_type = validate_upload(file.filename or "", data, max_bytes)
    except InvalidUpload as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return name, file_type.extension, file_type.mime_type, data


# ----------------------------------------------------------------- bibliotecas y carpetas
@router.get("/libraries", response_model=list[LibraryOut], tags=["libraries"])
def list_libraries(db: DbDep) -> list[LibraryOut]:
    return repo.list_libraries(db)


@router.get("/folders", response_model=list[FolderOut], tags=["folders"])
def list_folders(db: DbDep, library_id: str, parent_id: str | None = None) -> list[FolderOut]:
    try:
        return [FolderOut.model_validate(f) for f in repo.list_folders(db, library_id, parent_id)]
    except repo.NotFound as exc:
        raise _not_found(exc) from exc


@router.post("/folders", response_model=FolderOut, status_code=201, tags=["folders"])
def create_folder(body: FolderCreate, db: DbDep, actor: ActorDep) -> FolderOut:
    try:
        folder = repo.create_folder(
            db, library_id=body.library_id, parent_id=body.parent_id, name=body.name, actor=actor
        )
    except repo.NotFound as exc:
        raise _not_found(exc) from exc
    except repo.Invalid as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return FolderOut.model_validate(folder)


@router.get("/folders/{folder_id}/path", response_model=list[FolderOut], tags=["folders"])
def folder_path(folder_id: str, db: DbDep) -> list[FolderOut]:
    try:
        return [FolderOut.model_validate(f) for f in repo.folder_path(db, folder_id)]
    except repo.NotFound as exc:
        raise _not_found(exc) from exc


# ----------------------------------------------------------------- documentos
@router.get("/documents", response_model=DocumentPage, tags=["documents"])
def list_documents(
    db: DbDep,
    q: str | None = None,
    classification: Classification | None = None,
    library_id: str | None = None,
    folder_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentPage:
    return repo.list_documents(
        db,
        q=q,
        classification=classification,
        library_id=library_id,
        folder_id=folder_id,
        limit=limit,
        offset=offset,
    )


@router.post("/documents", response_model=DocumentMeta, status_code=201, tags=["documents"])
async def upload_document(
    db: DbDep,
    store: StoreDep,
    actor: ActorDep,
    settings: Annotated[Settings, Depends(_settings)],
    file: Annotated[UploadFile, File()],
    library_id: Annotated[str, Form()],
    classification: Annotated[Classification, Form()],
    folder_id: Annotated[str | None, Form()] = None,
    title: Annotated[str | None, Form(max_length=300)] = None,
) -> DocumentMeta | JSONResponse:
    name, ext, mime, data = await _read_upload(file, settings)
    try:
        doc = repo.create_document(
            db,
            store,
            library_id=library_id,
            folder_id=folder_id or None,
            filename=name,
            extension=ext,
            mime_type=mime,
            data=data,
            classification=classification,
            title=title,
            actor=actor,
        )
    except repo.NameConflict as exc:
        return JSONResponse(
            {"detail": str(exc), "code": "name_conflict", "document_id": exc.document_id},
            status_code=status.HTTP_409_CONFLICT,
        )
    except repo.NotFound as exc:
        raise _not_found(exc) from exc
    except repo.Invalid as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return repo.to_meta(doc)


@router.get("/documents/{doc_id}", response_model=DocumentMeta, tags=["documents"])
def get_document(doc_id: str, db: DbDep) -> DocumentMeta:
    try:
        return repo.to_meta(repo.get_document(db, doc_id))
    except repo.NotFound as exc:
        raise _not_found(exc) from exc


@router.patch(
    "/documents/{doc_id}",
    response_model=DocumentMeta,
    tags=["documents"],
    responses={409: {"description": "name_conflict: ya existe ese nombre en la carpeta"}},
)
def rename_document(
    doc_id: str, body: DocumentRename, db: DbDep, actor: ActorDep
) -> DocumentMeta | JSONResponse:
    """Renombra el archivo (no crea versión). La bitácora del cambio la registra share-api."""
    try:
        doc = repo.rename_document(db, repo.get_document(db, doc_id), body.name)
    except repo.NotFound as exc:
        raise _not_found(exc) from exc
    except repo.NameConflict as exc:
        return JSONResponse(
            {"detail": str(exc), "code": "name_conflict", "document_id": exc.document_id},
            status_code=status.HTTP_409_CONFLICT,
        )
    except repo.Invalid as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    del actor  # la autoría queda en la auditoría de share-api (X-Acting-User se exige igual)
    return repo.to_meta(doc)


@router.get("/documents/{doc_id}/versions", response_model=list[VersionOut], tags=["documents"])
def list_versions(doc_id: str, db: DbDep) -> list[VersionOut]:
    try:
        doc = repo.get_document(db, doc_id)
    except repo.NotFound as exc:
        raise _not_found(exc) from exc
    return [VersionOut.model_validate(v) for v in reversed(doc.versions)]


@router.post(
    "/documents/{doc_id}/versions", response_model=DocumentMeta, status_code=201, tags=["documents"]
)
async def upload_version(
    doc_id: str,
    db: DbDep,
    store: StoreDep,
    actor: ActorDep,
    settings: Annotated[Settings, Depends(_settings)],
    file: Annotated[UploadFile, File()],
    comment: Annotated[str, Form(max_length=500)] = "",
) -> DocumentMeta:
    _, ext, mime, data = await _read_upload(file, settings)
    try:
        doc = repo.get_document(db, doc_id)
        repo.add_version(
            db, store, doc, extension=ext, mime_type=mime, data=data, comment=comment, actor=actor
        )
    except repo.NotFound as exc:
        raise _not_found(exc) from exc
    except repo.Invalid as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return repo.to_meta(doc)


@router.get("/documents/{doc_id}/content", response_class=Response, tags=["documents"])
def get_document_content(
    doc_id: str, db: DbDep, store: StoreDep, version: int | None = None
) -> Response:
    try:
        doc = repo.get_document(db, doc_id)
        ver = repo.get_version(doc, version)
    except repo.NotFound as exc:
        raise _not_found(exc) from exc
    return Response(
        content=store.get(ver.storage_key),
        media_type=doc.mime_type,
        headers={
            "ETag": f'"{ver.sha256}"',
            "X-Content-SHA256": ver.sha256,
            "X-Document-Version": str(ver.version),
            "Content-Disposition": f'attachment; filename="{doc.id}.{_extension(doc.filename)}"',
        },
    )
