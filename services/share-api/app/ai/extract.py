"""Texto por página de los formatos que admite el DMS (PDF, DOCX, XLSX, TXT).

Una "página" es la unidad que se cita: página real en PDF, bloque de párrafos en DOCX y hoja en
XLSX. PDF escaneado o imagen: sin texto (el índice queda como EMPTY).
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PyPdfError

logger = logging.getLogger("share_api.ai")

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_DOCX_PARAGRAPHS_PER_PAGE = 40


@dataclass(frozen=True)
class PageText:
    page: int
    text: str


def _pdf(content: bytes) -> list[PageText]:
    reader = PdfReader(io.BytesIO(content))
    return [PageText(i + 1, (p.extract_text() or "").strip()) for i, p in enumerate(reader.pages)]


def _docx(content: bytes) -> list[PageText]:
    from docx import Document

    doc = Document(io.BytesIO(content))
    lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    step = _DOCX_PARAGRAPHS_PER_PAGE
    return [
        PageText(start // step + 1, "\n\n".join(lines[start : start + step]))
        for start in range(0, len(lines), step)
    ]


def _xlsx(content: bytes) -> list[PageText]:
    from openpyxl import load_workbook

    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    pages: list[PageText] = []
    for number, sheet in enumerate(workbook.worksheets, start=1):
        rows = []
        for row in sheet.iter_rows(values_only=True):
            cells = [str(v) for v in row if v not in (None, "")]
            if cells:
                rows.append(" | ".join(cells))
        pages.append(PageText(number, f"Hoja: {sheet.title}\n" + "\n".join(rows)))
    workbook.close()
    return pages


def extract_pages(content: bytes, mime_type: str) -> list[PageText]:
    """Páginas con texto. Lista vacía si el formato no tiene texto extraíble."""
    try:
        if mime_type == "application/pdf":
            pages = _pdf(content)
        elif mime_type == DOCX:
            pages = _docx(content)
        elif mime_type == XLSX:
            pages = _xlsx(content)
        elif mime_type.startswith("text/"):
            pages = [PageText(1, content.decode("utf-8", errors="replace"))]
        else:
            return []
    except (PyPdfError, ValueError, KeyError, OSError) as exc:
        logger.warning("no se pudo extraer texto", extra={"extra_fields": {"error": str(exc)}})
        return []
    return [p for p in pages if p.text.strip()]
