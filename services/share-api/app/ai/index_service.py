"""Índice de IA: sincroniza cada documento del DMS con sus fragmentos y embeddings.

``sync`` es idempotente: compara el sha256 vigente del DMS con lo indexado, actualiza la metadata
(nombre, carpeta, clasificación), indexa la versión nueva si hace falta y limpia lo eliminado.
Los cambios en la biblioteca encolan un trabajo (``enqueue``); lo procesan una tarea en segundo
plano tras la respuesta y, como respaldo, el job programado ``python -m app.ai.worker``.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.adapters.document_source import DocumentSource, SourceDocument
from app.ai.chunking import chunk_pages
from app.ai.extract import extract_pages
from app.ai.providers import Embedder
from app.core.config import Settings
from app.core.errors import NotFoundError
from app.db.models import AiChunk, AiIndex, AiJob

logger = logging.getLogger("share_api.ai")
MAX_ATTEMPTS = 3


def enqueue(db: Session, source_document_id: str) -> None:
    """Pide sincronizar el documento. Un solo pendiente por documento (índice parcial único)."""
    db.execute(
        insert(AiJob)
        .values(source_document_id=source_document_id, status="PENDING")
        .on_conflict_do_nothing(
            index_elements=["source_document_id"], index_where=text("status = 'PENDING'")
        )
    )


@dataclass
class IndexService:
    db: Session
    settings: Settings
    source: DocumentSource
    embedder: Embedder

    # ------------------------------------------------------------------ cola
    def run_pending(self, limit: int = 20) -> int:
        """Procesa trabajos pendientes. Devuelve cuántos se procesaron."""
        processed = 0
        while processed < limit:
            job = self.db.scalar(
                select(AiJob)
                .where(AiJob.status == "PENDING")
                .order_by(AiJob.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if job is None:
                break
            try:
                self.sync(job.source_document_id)
                job.status = "DONE"
            except Exception as exc:  # un documento problemático no detiene la cola
                job.attempts += 1
                job.last_error = str(exc)[:500]
                job.status = "FAILED" if job.attempts >= MAX_ATTEMPTS else "PENDING"
                logger.warning(
                    "falló la indexación",
                    extra={"extra_fields": {"document": job.source_document_id, "error": str(exc)}},
                )
                if job.status == "PENDING":
                    self.db.commit()
                    break  # se reintenta en la próxima pasada
            self.db.commit()
            processed += 1
        return processed

    def enqueue_all(self) -> int:
        """Encola todos los documentos del DMS (backfill o cambio de modelo de embeddings)."""
        offset, total = 0, 0
        while True:
            page = self.source.list(q=None, limit=200, offset=offset)
            for doc in page.items:
                enqueue(self.db, doc.id)
            total += len(page.items)
            offset += len(page.items)
            if not page.items or offset >= page.total:
                break
        self.db.commit()
        return total

    # ------------------------------------------------------------------ sincronización
    def sync(self, source_document_id: str) -> AiIndex | None:
        try:
            meta = self.source.get_metadata(source_document_id)
        except NotFoundError:
            # Eliminado en el DMS: se borra todo lo indexado (los fragmentos caen en cascada).
            self.db.execute(delete(AiIndex).where(AiIndex.source_document_id == source_document_id))
            return None

        self.db.execute(
            update(AiIndex)
            .where(AiIndex.source_document_id == meta.id, AiIndex.sha256 != meta.sha256)
            .values(is_current=False)
        )
        row = self.db.scalar(
            select(AiIndex).where(
                AiIndex.source_document_id == meta.id, AiIndex.sha256 == meta.sha256
            )
        )
        if row is None:
            row = AiIndex(source_document_id=meta.id, sha256=meta.sha256, status="PENDING")
            self.db.add(row)
        self._apply_metadata(row, meta)
        row.is_current = True

        if self.settings.ai_exclude_restricted and meta.classification.value == "RESTRICTED":
            self.db.flush()
            self.db.execute(delete(AiChunk).where(AiChunk.index_id == row.id))
            row.status, row.chunk_count = "SKIPPED", 0
            row.error = "Documento RESTRINGIDO: excluido de la IA por política"
            return row
        if row.status == "INDEXED" and row.embedding_model == self.embedder.model:
            return row  # solo cambió la metadata

        content = self.source.get_content(meta.id)
        if hashlib.sha256(content).hexdigest() != meta.sha256:
            raise ValueError("El contenido no coincide con el hash publicado por el DMS")
        self.db.flush()
        self.index_content(row, content)
        return row

    def index_snapshot(self, *, source_document_id: str, sha256: str, content: bytes) -> AiIndex:
        """Indexa una versión anterior compartida (para las preguntas del destinatario)."""
        row = self.db.scalar(
            select(AiIndex).where(
                AiIndex.source_document_id == source_document_id, AiIndex.sha256 == sha256
            )
        )
        if row is not None and row.status in ("INDEXED", "EMPTY", "SKIPPED"):
            return row
        meta = self.source.get_metadata(source_document_id)
        if row is None:
            row = AiIndex(source_document_id=source_document_id, sha256=sha256, is_current=False)
            self.db.add(row)
            self._apply_metadata(row, meta)
            row.version = 0
        self.db.flush()
        self.index_content(row, content)
        return row

    def _apply_metadata(self, row: AiIndex, meta: SourceDocument) -> None:
        row.version = meta.version
        row.title = meta.title
        row.filename = meta.filename or meta.id
        row.mime_type = meta.mime_type
        row.library_id = meta.library_id
        row.folder_id = meta.folder_id
        row.classification = meta.classification.value

    def index_content(self, row: AiIndex, content: bytes) -> None:
        pages = extract_pages(content, row.mime_type)
        chunks = chunk_pages(
            pages,
            max_tokens=self.settings.ai_chunk_tokens,
            overlap=self.settings.ai_chunk_overlap_tokens,
        )
        self.db.execute(delete(AiChunk).where(AiChunk.index_id == row.id))
        now = datetime.now(UTC)
        if not chunks:
            row.status, row.chunk_count, row.error = "EMPTY", 0, "Sin texto extraíble"
            row.indexed_at = now
            return
        # El título acompaña a cada fragmento al calcular el embedding (mejora la recuperación).
        vectors = self.embedder.embed_documents([f"{row.title}\n\n{c.text}" for c in chunks])
        self.db.add_all(
            AiChunk(
                index_id=row.id,
                chunk_index=c.index,
                page_from=c.page_from,
                page_to=c.page_to,
                text=c.text,
                embedding=v,
            )
            for c, v in zip(chunks, vectors, strict=True)
        )
        row.status, row.chunk_count, row.error = "INDEXED", len(chunks), None
        row.embedding_model = self.embedder.model
        row.indexed_at = now


def current_status(db: Session, source_document_id: str) -> AiIndex | None:
    return db.scalar(
        select(AiIndex).where(
            AiIndex.source_document_id == source_document_id, AiIndex.is_current.is_(True)
        )
    )
