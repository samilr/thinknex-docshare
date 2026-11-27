"""Seed idempotente: bibliotecas, carpetas y documentos ficticios (con historial de versiones)."""

import hashlib
import io
import json
import logging
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Document, DocumentVersion, Folder, Library
from app.schemas import SeedCatalog, SeedDocument
from app.storage import BlobStore

logger = logging.getLogger(__name__)
SEED_ACTOR = "sistema@thinknex.example"


def load_catalog(path: Path) -> SeedCatalog:
    return SeedCatalog.model_validate(json.loads(path.read_text(encoding="utf-8")))


def render_pdf(entry: SeedDocument, version: int | None = None) -> bytes:
    version = version or entry.version
    buffer = io.BytesIO()
    # invariant=1 hace la salida determinista: mismo contenido => mismo sha256 entre reinicios.
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, title=entry.title, author="ThinkNex (ficticio)", invariant=1
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph(entry.title, styles["Title"]),
        Paragraph(
            f"Clasificación: {entry.classification.value} · Versión {version}", styles["Italic"]
        ),
        Spacer(1, 16),
    ]
    if version < entry.version:
        story.append(Paragraph("BORRADOR: versión anterior, reemplazada.", styles["Heading4"]))
    for paragraph in entry.paragraphs:
        story.append(Paragraph(paragraph, styles["BodyText"]))
        story.append(Spacer(1, 8))
    doc.build(story)
    return buffer.getvalue()


def seed(db: Session, store: BlobStore, catalog: SeedCatalog) -> int:
    folders: dict[tuple[str, str], str] = {}
    for position, lib in enumerate(catalog.libraries):
        if db.get(Library, lib.id) is None:
            db.add(
                Library(id=lib.id, name=lib.name, description=lib.description, position=position)
            )
            db.flush()
        for name in lib.folders:
            folder = db.scalar(
                select(Folder).where(
                    Folder.library_id == lib.id, Folder.parent_id.is_(None), Folder.name == name
                )
            )
            if folder is None:
                folder = Folder(library_id=lib.id, parent_id=None, name=name, created_by=SEED_ACTOR)
                db.add(folder)
                db.flush()
            folders[(lib.id, name)] = folder.id

    created = 0
    for entry in catalog.documents:
        if db.get(Document, entry.id) is not None:
            continue
        doc = Document(
            id=entry.id,
            library_id=entry.library,
            folder_id=folders[(entry.library, entry.folder)] if entry.folder else None,
            title=entry.title,
            filename=entry.filename,
            mime_type="application/pdf",
            classification=entry.classification.value,
            owner=entry.owner,
            current_version=entry.version,
            created_by=entry.owner,
        )
        for version in range(1, entry.version + 1):
            data = render_pdf(entry, version)
            key = f"{entry.id}/v{version}.pdf"
            # Se sobrescribe siempre: el hash registrado debe corresponder al objeto guardado.
            store.put(key, data, "application/pdf")
            doc.versions.append(
                DocumentVersion(
                    version=version,
                    sha256=hashlib.sha256(data).hexdigest(),
                    size_bytes=len(data),
                    storage_key=key,
                    created_by=entry.owner,
                    comment="Versión inicial" if version == 1 else "Actualización",
                )
            )
        db.add(doc)
        created += 1
    try:
        db.commit()
    except IntegrityError:  # otra instancia sembró al mismo tiempo: su resultado es equivalente
        db.rollback()
        logger.info("seed realizado por otra instancia")
        return 0
    logger.info("seed completado: %s documentos nuevos", created)
    return created
