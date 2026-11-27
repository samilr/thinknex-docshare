"""Recuperación híbrida con permisos: vectores (pgvector) + texto completo en español, con RRF.

El filtro de permisos y de alcance va en el SQL: el modelo nunca recibe fragmentos de documentos
que quien pregunta no puede abrir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import Select, func, select, text
from sqlalchemy.orm import Session

from app.ai.providers import Embedder
from app.db.models import AiChunk, AiIndex

RRF_K = 60


@dataclass(frozen=True)
class Scope:
    """Qué fragmentos se pueden recuperar.

    Usuarios internos: versiones vigentes indexadas, opcionalmente acotadas a biblioteca, carpeta o
    documentos. Destinatario: un único índice (la versión compartida).
    """

    library_id: str | None = None
    folder_id: str | None = None
    document_ids: tuple[str, ...] = ()
    index_id: int | None = None


@dataclass
class Hit:
    chunk_id: int
    source_document_id: str
    title: str
    filename: str
    library_id: str | None
    folder_id: str | None
    classification: str
    version: int
    page_from: int
    page_to: int
    text: str
    score: float = 0.0
    sources: list[str] = field(default_factory=list)


def _filtered(stmt: Select, scope: Scope) -> Select:  # type: ignore[type-arg]
    stmt = stmt.join(AiIndex, AiIndex.id == AiChunk.index_id).where(AiIndex.status == "INDEXED")
    if scope.index_id is not None:
        return stmt.where(AiIndex.id == scope.index_id)
    stmt = stmt.where(AiIndex.is_current.is_(True))
    if scope.library_id:
        stmt = stmt.where(AiIndex.library_id == scope.library_id)
    if scope.folder_id:
        stmt = stmt.where(AiIndex.folder_id == scope.folder_id)
    if scope.document_ids:
        stmt = stmt.where(AiIndex.source_document_id.in_(scope.document_ids))
    return stmt


def search(
    db: Session,
    embedder: Embedder,
    query: str,
    scope: Scope,
    *,
    limit: int = 8,
    candidates: int = 30,
) -> list[Hit]:
    query = query.strip()
    if not query:
        return []
    db.execute(text("SET LOCAL hnsw.ef_search = 100"))
    vector = embedder.embed_query(query)
    distance = AiChunk.embedding.cosine_distance(vector)
    by_vector = db.execute(
        _filtered(select(AiChunk.id), scope).order_by(distance).limit(candidates)
    ).scalars()
    tsquery = func.websearch_to_tsquery("spanish", query)
    by_text = db.execute(
        _filtered(select(AiChunk.id), scope)
        .where(AiChunk.tsv.op("@@")(tsquery))
        .order_by(func.ts_rank_cd(AiChunk.tsv, tsquery).desc())
        .limit(candidates)
    ).scalars()

    scores: dict[int, float] = {}
    sources: dict[int, list[str]] = {}
    for name, ranking in (("semántica", list(by_vector)), ("texto", list(by_text))):
        for rank, chunk_id in enumerate(ranking):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
            sources.setdefault(chunk_id, []).append(name)
    best = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:limit]
    if not best:
        return []
    rows = db.execute(
        select(AiChunk, AiIndex)
        .join(AiIndex, AiIndex.id == AiChunk.index_id)
        .where(AiChunk.id.in_(best))
    ).all()
    by_id = {chunk.id: (chunk, index) for chunk, index in rows}
    hits: list[Hit] = []
    for chunk_id in best:
        chunk, index = by_id[chunk_id]
        hits.append(
            Hit(
                chunk_id=chunk.id,
                source_document_id=index.source_document_id,
                title=index.title,
                filename=index.filename,
                library_id=index.library_id,
                folder_id=index.folder_id,
                classification=index.classification,
                version=index.version,
                page_from=chunk.page_from,
                page_to=chunk.page_to,
                text=chunk.text,
                score=round(scores[chunk_id], 5),
                sources=sources[chunk_id],
            )
        )
    return hits
