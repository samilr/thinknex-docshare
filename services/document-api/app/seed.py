"""Genera los PDFs ficticios del catálogo y los sube al almacenamiento si no existen."""

import io
import logging

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from app.catalog import SeedEntry
from app.storage import BlobStore

logger = logging.getLogger(__name__)


def render_pdf(entry: SeedEntry) -> bytes:
    buffer = io.BytesIO()
    # invariant=1 hace la salida determinista: mismo contenido => mismo sha256 entre reinicios.
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, title=entry.title, author="ThinkNex (ficticio)", invariant=1
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph(entry.title, styles["Title"]),
        Paragraph(
            f"Clasificación: {entry.classification.value} · Versión {entry.version}",
            styles["Italic"],
        ),
        Spacer(1, 16),
    ]
    for paragraph in entry.paragraphs:
        story.append(Paragraph(paragraph, styles["BodyText"]))
        story.append(Spacer(1, 8))
    doc.build(story)
    return buffer.getvalue()


def seed(store: BlobStore, entries: list[SeedEntry]) -> int:
    created = 0
    for entry in entries:
        if store.exists(entry.storage_key):
            continue
        store.put(entry.storage_key, render_pdf(entry), "application/pdf")
        created += 1
    logger.info("seed completado: %s documentos nuevos de %s", created, len(entries))
    return created
