"""Marca de agua generada al vuelo en cada descarga (nunca se almacena)."""

import io

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas


def _overlay(width: float, height: float, text: str) -> PdfReader:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))
    c.setFillColor(Color(0.75, 0.1, 0.1, alpha=0.35))
    c.setFont("Helvetica-Bold", 14)
    c.saveState()
    c.translate(width / 2, height / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, text)
    c.restoreState()
    c.setFont("Helvetica", 7)
    c.drawString(24, 16, text)
    c.save()
    buffer.seek(0)
    return PdfReader(buffer)


def watermark_pdf(content: bytes, text: str) -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(content)))
    for page in writer.pages:
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        page.merge_page(_overlay(width, height, text).pages[0])
    writer.add_metadata({"/Subject": text})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def apply_watermark(content: bytes, mime_type: str, text: str) -> tuple[bytes, bool]:
    """Devuelve (contenido, se_aplicó). Formatos no PDF se entregan sin marca (limitación)."""
    if mime_type == "application/pdf":
        return watermark_pdf(content, text), True
    return content, False
