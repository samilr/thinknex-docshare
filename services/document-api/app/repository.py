"""Casos de uso del sistema documental sobre la BD y el almacenamiento de objetos."""

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Document, DocumentVersion, Folder, Library
from app.schemas import Classification, DocumentMeta, DocumentPage, LibraryOut
from app.storage import BlobStore
from app.validation import InvalidUpload, safe_filename


class NotFound(LookupError):
    pass


class NameConflict(Exception):
    def __init__(self, document_id: str) -> None:
        super().__init__("Ya existe un archivo con ese nombre en esta ubicación")
        self.document_id = document_id


class Invalid(ValueError):
    pass


def to_meta(doc: Document) -> DocumentMeta:
    current = doc.current
    return DocumentMeta(
        id=doc.id,
        title=doc.title,
        filename=doc.filename,
        mime_type=doc.mime_type,
        size_bytes=current.size_bytes,
        sha256=current.sha256,
        version=doc.current_version,
        classification=Classification(doc.classification),
        owner=doc.owner,
        library_id=doc.library_id,
        folder_id=doc.folder_id,
        created_by=doc.created_by,
        updated_at=doc.updated_at,
    )


# ----------------------------------------------------------------- bibliotecas y carpetas
def list_libraries(db: Session) -> list[LibraryOut]:
    rows = db.execute(
        select(Document.library_id, func.count(Document.id))
        .where(Document.deleted_at.is_(None))
        .group_by(Document.library_id)
    )
    counts = {library_id: count for library_id, count in rows}
    return [
        LibraryOut(
            id=lib.id,
            name=lib.name,
            description=lib.description,
            document_count=int(counts.get(lib.id, 0)),
        )
        for lib in db.scalars(select(Library).order_by(Library.position, Library.name))
    ]


def get_library(db: Session, library_id: str) -> Library:
    library = db.get(Library, library_id)
    if library is None:
        raise NotFound("Biblioteca no encontrada")
    return library


def get_folder(db: Session, folder_id: str) -> Folder:
    folder = db.get(Folder, folder_id)
    if folder is None:
        raise NotFound("Carpeta no encontrada")
    return folder


def _check_location(db: Session, library_id: str, folder_id: str | None) -> None:
    get_library(db, library_id)
    if folder_id is not None and get_folder(db, folder_id).library_id != library_id:
        raise Invalid("La carpeta no pertenece a la biblioteca")


def list_folders(db: Session, library_id: str, parent_id: str | None) -> list[Folder]:
    get_library(db, library_id)
    stmt = select(Folder).where(Folder.library_id == library_id)
    stmt = stmt.where(
        Folder.parent_id.is_(None) if parent_id is None else Folder.parent_id == parent_id
    )
    return list(db.scalars(stmt.order_by(Folder.name)))


def create_folder(
    db: Session, *, library_id: str, parent_id: str | None, name: str, actor: str
) -> Folder:
    _check_location(db, library_id, parent_id)
    clean = name.strip()
    if not clean or any(c in clean for c in "/\\"):
        raise Invalid("Nombre de carpeta inválido")
    siblings = list_folders(db, library_id, parent_id)
    if any(f.name.casefold() == clean.casefold() for f in siblings):
        raise Invalid("Ya existe una carpeta con ese nombre")
    folder = Folder(library_id=library_id, parent_id=parent_id, name=clean, created_by=actor)
    db.add(folder)
    db.flush()
    return folder


def folder_path(db: Session, folder_id: str) -> list[Folder]:
    path: list[Folder] = []
    current: Folder | None = get_folder(db, folder_id)
    while current is not None and len(path) < 50:
        path.append(current)
        current = db.get(Folder, current.parent_id) if current.parent_id else None
    return list(reversed(path))


# ----------------------------------------------------------------- documentos
def list_documents(
    db: Session,
    *,
    q: str | None,
    classification: Classification | None,
    library_id: str | None,
    folder_id: str | None,
    limit: int,
    offset: int,
) -> DocumentPage:
    stmt = select(Document).where(Document.deleted_at.is_(None))
    if library_id:
        # En una biblioteca se listan los archivos de la carpeta indicada (o de la raíz).
        stmt = stmt.where(Document.library_id == library_id)
        if not q:
            stmt = stmt.where(
                Document.folder_id.is_(None)
                if folder_id is None
                else Document.folder_id == folder_id
            )
    if q:
        like = f"%{q.casefold()}%"
        stmt = stmt.where(
            or_(func.lower(Document.title).like(like), func.lower(Document.filename).like(like))
        )
    if classification:
        stmt = stmt.where(Document.classification == classification.value)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    docs = db.scalars(stmt.order_by(Document.title).limit(limit).offset(offset))
    return DocumentPage(items=[to_meta(d) for d in docs], total=total, limit=limit, offset=offset)


def get_document(db: Session, doc_id: str) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None or doc.deleted_at is not None:
        raise NotFound("Documento no encontrado")
    return doc


def get_version(doc: Document, version: int | None) -> DocumentVersion:
    wanted = version or doc.current_version
    for v in doc.versions:
        if v.version == wanted:
            return v
    raise NotFound("Versión no encontrada")


def _store_version(
    store: BlobStore, doc_id: str, version: int, ext: str, data: bytes, mime: str
) -> tuple[str, str]:
    key = f"{doc_id}/v{version}.{ext}"
    store.put(key, data, mime)
    return key, hashlib.sha256(data).hexdigest()


def create_document(
    db: Session,
    store: BlobStore,
    *,
    library_id: str,
    folder_id: str | None,
    filename: str,
    extension: str,
    mime_type: str,
    data: bytes,
    classification: Classification,
    title: str | None,
    actor: str,
) -> Document:
    _check_location(db, library_id, folder_id)
    existing = db.scalar(
        select(Document).where(
            Document.library_id == library_id,
            Document.folder_id.is_(None) if folder_id is None else Document.folder_id == folder_id,
            func.lower(Document.filename) == filename.casefold(),
            Document.deleted_at.is_(None),
        )
    )
    if existing is not None:
        raise NameConflict(existing.id)
    doc_id = f"doc-{uuid.uuid4().hex[:8]}"
    key, sha = _store_version(store, doc_id, 1, extension, data, mime_type)
    now = datetime.now(UTC)
    doc = Document(
        id=doc_id,
        library_id=library_id,
        folder_id=folder_id,
        title=(title or filename.rsplit(".", 1)[0]).strip()[:300],
        filename=filename,
        mime_type=mime_type,
        classification=classification.value,
        owner=actor,
        current_version=1,
        created_by=actor,
        created_at=now,
        updated_at=now,
    )
    doc.versions.append(
        DocumentVersion(
            version=1,
            sha256=sha,
            size_bytes=len(data),
            storage_key=key,
            created_by=actor,
            comment="",
        )
    )
    db.add(doc)
    db.flush()
    return doc


def add_version(
    db: Session,
    store: BlobStore,
    doc: Document,
    *,
    extension: str,
    mime_type: str,
    data: bytes,
    comment: str,
    actor: str,
) -> Document:
    if mime_type != doc.mime_type:
        raise Invalid("La nueva versión debe ser del mismo tipo de archivo")
    version = doc.current_version + 1
    key, sha = _store_version(store, doc.id, version, extension, data, mime_type)
    doc.versions.append(
        DocumentVersion(
            version=version,
            sha256=sha,
            size_bytes=len(data),
            storage_key=key,
            created_by=actor,
            comment=comment.strip()[:500],
        )
    )
    doc.current_version = version
    doc.updated_at = datetime.now(UTC)
    db.flush()
    return doc


def update_document(
    db: Session, doc: Document, *, name: str | None, classification: Classification | None
) -> Document:
    """Cambia nombre y/o clasificación. No crea versión: el contenido no cambia."""
    if name is not None:
        rename_document(db, doc, name)
    if classification is not None and classification.value != doc.classification:
        doc.classification = classification.value
        doc.updated_at = datetime.now(UTC)
        db.flush()
    return doc


def delete_document(db: Session, doc: Document, actor: str) -> None:
    """Eliminación lógica: deja de listarse y de servirse; se conservan versiones y metadata."""
    now = datetime.now(UTC)
    doc.deleted_at = now
    doc.deleted_by = actor
    doc.updated_at = now
    db.flush()


def rename_document(db: Session, doc: Document, name: str) -> Document:
    """Cambia el nombre visible y el nombre de archivo, conservando la extensión.

    No crea una versión: el contenido no cambia. Un nombre repetido en la misma carpeta es un
    conflicto, igual que al subir.
    """
    extension = doc.filename.rsplit(".", 1)[-1]
    try:
        filename = safe_filename(f"{name.strip()}.{extension}")
    except InvalidUpload as exc:
        raise Invalid("Nombre inválido") from exc
    existing = db.scalar(
        select(Document).where(
            Document.id != doc.id,
            Document.library_id == doc.library_id,
            Document.folder_id.is_(None)
            if doc.folder_id is None
            else Document.folder_id == doc.folder_id,
            func.lower(Document.filename) == filename.casefold(),
            Document.deleted_at.is_(None),
        )
    )
    if existing is not None:
        raise NameConflict(existing.id)
    doc.filename = filename
    doc.title = filename.rsplit(".", 1)[0]
    doc.updated_at = datetime.now(UTC)
    db.flush()
    return doc
