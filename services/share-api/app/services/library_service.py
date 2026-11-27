"""Biblioteca de documentos para el portal (estilo SharePoint).

Orquesta el sistema documental (bibliotecas, carpetas, archivos y versiones) con lo que solo
share-api conoce: quién tiene acceso a cada archivo (shares), su actividad (auditoría) y la vista
interna con marca de agua. Toda acción queda auditada.
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.document_source import (
    DocumentSource,
    SourceDocument,
    SourceFolder,
    SourceLibrary,
    SourceVersion,
    UploadedFile,
)
from app.adapters.watermark import apply_watermark
from app.core.config import Settings
from app.core.errors import NotFoundError, UpstreamError
from app.db.models import AuditEvent, Document, Share, User
from app.domain.enums import ActorType, AuditEventType, Classification, ShareStatus
from app.schemas import ShareOut
from app.sensitivity.detectors import FindingSummary, detect, extract_text, summarize
from app.services import audit_service
from app.services.context import RequestContext
from app.services.share_service import to_share_out


class LibraryDocument(SourceDocument):
    active_shares: int = 0


class LibraryItems(BaseModel):
    library: SourceLibrary
    breadcrumbs: list[SourceFolder]
    folders: list[SourceFolder]
    documents: list[LibraryDocument]


class DocumentDetail(BaseModel):
    document: LibraryDocument
    versions: list[SourceVersion]
    library: SourceLibrary | None
    breadcrumbs: list[SourceFolder]


class UploadResult(BaseModel):
    document: LibraryDocument
    findings: list[FindingSummary]
    new_version: bool


@dataclass(frozen=True)
class ContentPayload:
    content: bytes
    filename: str
    mime_type: str


@dataclass
class LibraryService:
    db: Session
    settings: Settings
    source: DocumentSource

    # ------------------------------------------------------------------ helpers
    def _audit(
        self,
        event: AuditEventType,
        user: User,
        ctx: RequestContext,
        **details: Any,
    ) -> None:
        audit_service.record(
            self.db,
            event_type=event,
            actor_type=ActorType.USER,
            actor_id=user.id,
            ctx=ctx,
            details=details,
        )

    def _active_shares(self, source_ids: list[str]) -> dict[str, int]:
        if not source_ids:
            return {}
        rows = self.db.execute(
            select(Document.source_id, func.count(Share.id))
            .join(Share, Share.document_id == Document.id)
            .where(
                Document.source_id.in_(source_ids),
                Share.status == ShareStatus.ACTIVE.value,
                Share.expires_at > func.now(),
            )
            .group_by(Document.source_id)
        )
        return {source_id: int(count) for source_id, count in rows}

    def _with_shares(self, docs: list[SourceDocument]) -> list[LibraryDocument]:
        counts = self._active_shares([d.id for d in docs])
        return [LibraryDocument(**d.model_dump(), active_shares=counts.get(d.id, 0)) for d in docs]

    def _library(self, library_id: str) -> SourceLibrary:
        for library in self.source.libraries():
            if library.id == library_id:
                return library
        raise NotFoundError("Biblioteca no encontrada")

    @staticmethod
    def _findings(data: bytes, mime_type: str) -> list[FindingSummary]:
        text = extract_text(data, mime_type)
        return summarize(detect(text)) if text else []

    # ------------------------------------------------------------------ navegación
    def libraries(self) -> list[SourceLibrary]:
        return self.source.libraries()

    def items(self, library_id: str, folder_id: str | None, q: str | None) -> LibraryItems:
        library = self._library(library_id)
        breadcrumbs = self.source.folder_path(folder_id) if folder_id else []
        if breadcrumbs and breadcrumbs[-1].library_id != library_id:
            raise NotFoundError("Carpeta no encontrada en esta biblioteca")
        folders = [] if q else self.source.folders(library_id, folder_id)
        page = self.source.list(
            q=q, limit=200, offset=0, library_id=library_id, folder_id=folder_id
        )
        return LibraryItems(
            library=library,
            breadcrumbs=breadcrumbs,
            folders=folders,
            documents=self._with_shares(page.items),
        )

    def create_folder(
        self, user: User, library_id: str, parent_id: str | None, name: str, ctx: RequestContext
    ) -> SourceFolder:
        folder = self.source.create_folder(
            library_id=library_id, parent_id=parent_id, name=name, actor=user.email
        )
        self._audit(
            AuditEventType.FOLDER_CREATED,
            user,
            ctx,
            library_id=library_id,
            folder_id=folder.id,
            name=folder.name,
        )
        return folder

    # ------------------------------------------------------------------ archivos
    def upload(
        self,
        user: User,
        file: UploadedFile,
        *,
        library_id: str,
        folder_id: str | None,
        classification: Classification,
        title: str | None,
        ctx: RequestContext,
    ) -> UploadResult:
        document = self.source.upload(
            file=file,
            library_id=library_id,
            folder_id=folder_id,
            classification=classification,
            title=title,
            actor=user.email,
        )
        findings = self._findings(file.data, document.mime_type)
        self._audit(
            AuditEventType.DOCUMENT_UPLOADED,
            user,
            ctx,
            source_document_id=document.id,
            version=document.version,
            sha256=document.sha256,
            classification=document.classification.value,
            library_id=library_id,
            findings={f.type: f.count for f in findings},
        )
        return UploadResult(
            document=self._with_shares([document])[0], findings=findings, new_version=False
        )

    def upload_version(
        self, user: User, doc_id: str, file: UploadedFile, comment: str, ctx: RequestContext
    ) -> UploadResult:
        document = self.source.upload_version(doc_id, file=file, comment=comment, actor=user.email)
        findings = self._findings(file.data, document.mime_type)
        self._audit(
            AuditEventType.DOCUMENT_VERSION_UPLOADED,
            user,
            ctx,
            source_document_id=document.id,
            version=document.version,
            sha256=document.sha256,
            comment=comment,
            findings={f.type: f.count for f in findings},
        )
        return UploadResult(
            document=self._with_shares([document])[0], findings=findings, new_version=True
        )

    def rename(self, user: User, doc_id: str, name: str, ctx: RequestContext) -> LibraryDocument:
        """Renombra el archivo en el DMS y deja en la bitácora el nombre anterior, el nuevo y quién.

        No altera lo ya compartido: cada envío conserva el título de su snapshot (ADR-0002).
        """
        before = self.source.get_metadata(doc_id)
        after = self.source.rename(doc_id, name=name, actor=user.email)
        if (after.title, after.filename) != (before.title, before.filename):
            self._audit(
                AuditEventType.DOCUMENT_RENAMED,
                user,
                ctx,
                source_document_id=doc_id,
                version=after.version,
                from_title=before.title,
                to_title=after.title,
                from_filename=before.filename,
                to_filename=after.filename,
            )
        return self._with_shares([after])[0]

    def detail(self, doc_id: str) -> DocumentDetail:
        document = self.source.get_metadata(doc_id)
        library = (
            next((lib for lib in self.source.libraries() if lib.id == document.library_id), None)
            if document.library_id
            else None
        )
        breadcrumbs = self.source.folder_path(document.folder_id) if document.folder_id else []
        return DocumentDetail(
            document=self._with_shares([document])[0],
            versions=self.source.versions(doc_id),
            library=library,
            breadcrumbs=breadcrumbs,
        )

    def content(
        self,
        user: User,
        doc_id: str,
        *,
        version: int | None,
        disposition: str,
        ctx: RequestContext,
    ) -> ContentPayload:
        document = self.source.get_metadata(doc_id)
        versions = {v.version: v for v in self.source.versions(doc_id)}
        wanted = version or document.version
        if wanted not in versions:
            raise NotFoundError("Versión no encontrada")
        data = self.source.get_content(doc_id, wanted)
        if hashlib.sha256(data).hexdigest() != versions[wanted].sha256:
            raise UpstreamError("El contenido no coincide con el hash publicado por el DMS")
        stamp = f"Vista interna · {user.email} · {datetime.now(UTC):%Y-%m-%d %H:%M} UTC"
        payload, watermarked = apply_watermark(data, document.mime_type, stamp)
        self._audit(
            AuditEventType.DOCUMENT_VIEWED,
            user,
            ctx,
            source_document_id=doc_id,
            version=wanted,
            mode="download" if disposition == "attachment" else "preview",
            watermarked=watermarked,
        )
        name = document.filename or f"{doc_id}.bin"
        if wanted != document.version and "." in name:
            stem, ext = name.rsplit(".", 1)
            name = f"{stem} (v{wanted}).{ext}"
        return ContentPayload(payload, name, document.mime_type)

    def access(self, doc_id: str) -> list[ShareOut]:
        """Personas con acceso: envíos del archivo, primero los vigentes."""
        shares = self.db.scalars(
            select(Share)
            .join(Document, Share.document_id == Document.id)
            .where(Document.source_id == doc_id)
            .order_by(Share.created_at.desc())
        ).unique()
        rows = [to_share_out(s) for s in shares]
        return sorted(rows, key=lambda s: s.status is not ShareStatus.ACTIVE)

    def activity(self, doc_id: str, limit: int = 100) -> list[AuditEvent]:
        rows, _ = audit_service.query(
            self.db,
            audit_service.AuditFilters(source_document_id=doc_id),
            limit=limit,
            offset=0,
        )
        return rows
