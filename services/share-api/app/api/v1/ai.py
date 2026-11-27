"""IA para usuarios internos: búsqueda semántica y preguntas con citas sobre los documentos."""

import json
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.ai import usage as ai_usage
from app.ai.answer_service import AnswerStream, protect, source_out
from app.ai.llm import Usage
from app.ai.retrieval import Scope, search
from app.api.deps import (
    ComponentsDep,
    ContextDep,
    CurrentUserDep,
    DbDep,
    LibraryUserDep,
    SettingsDep,
)
from app.core.errors import DomainError
from app.domain.enums import ActorType, AuditEventType
from app.services import audit_service

router = APIRouter(prefix="/ai", tags=["ia"])


class AiUnavailableError(DomainError):
    status_code = 503
    code = "ai_unavailable"
    title = "La IA no está disponible en este entorno"


class AiStatusOut(BaseModel):
    enabled: bool
    llm: bool
    chat_model: str | None


class SourceOut(BaseModel):
    n: int
    document_id: str
    title: str
    filename: str
    library_id: str | None
    folder_id: str | None
    page_from: int
    page_to: int
    snippet: str
    score: float


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    library_id: str | None = None
    folder_id: str | None = None
    document_ids: list[str] = Field(default_factory=list, max_length=20)


def sse(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_response(events: Iterator[tuple[str, dict[str, Any]]]) -> StreamingResponse:
    return StreamingResponse(
        (sse(name, data) for name, data in events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get("/status", response_model=AiStatusOut)
def status(_: CurrentUserDep, settings: SettingsDep, components: ComponentsDep) -> AiStatusOut:
    llm = settings.ai_enabled and components.llm is not None
    return AiStatusOut(
        enabled=settings.ai_enabled, llm=llm, chat_model=settings.ai_chat_model if llm else None
    )


@router.get("/search", response_model=list[SourceOut])
def semantic_search(
    q: Annotated[str, Query(min_length=2, max_length=500)],
    _: LibraryUserDep,
    db: DbDep,
    settings: SettingsDep,
    components: ComponentsDep,
    library_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=30)] = 10,
) -> list[SourceOut]:
    """Búsqueda híbrida (semántica + texto) en los documentos visibles. No usa el LLM."""
    if not settings.ai_enabled:
        raise AiUnavailableError()
    hits = search(db, components.embedder, q, Scope(library_id=library_id), limit=limit)
    return [SourceOut(**source_out(i + 1, h)) for i, h in enumerate(hits)]


@router.post("/ask", response_class=StreamingResponse)
def ask(
    body: AskRequest,
    user: LibraryUserDep,
    db: DbDep,
    settings: SettingsDep,
    components: ComponentsDep,
    ctx: ContextDep,
) -> StreamingResponse:
    """Pregunta sobre los documentos. Streaming SSE: sources, text, citation, done."""
    if not settings.ai_enabled or components.llm is None:
        raise AiUnavailableError()
    ai_usage.ensure_budget(db, user.id, settings.ai_daily_token_budget)
    scope = Scope(
        library_id=body.library_id,
        folder_id=body.folder_id,
        document_ids=tuple(body.document_ids),
    )
    hits = search(db, components.embedder, body.question, scope)
    audit_service.record(
        db,
        event_type=AuditEventType.AI_QUERY,
        actor_type=ActorType.USER,
        actor_id=user.id,
        ctx=ctx,
        details={
            "feature": "ask",
            "question": protect(body.question)[:500],
            "documents": sorted({h.source_document_id for h in hits}),
            "fragments": len(hits),
        },
    )
    user_id = user.id

    def on_done(usage: Usage) -> None:
        with components.session_factory() as session, session.begin():
            ai_usage.record(session, user_id, "ask", usage)

    answer = AnswerStream(
        llm=components.llm,
        model=settings.ai_chat_model,
        question=body.question,
        hits=hits,
        redact_pii=settings.ai_redact_pii,
        on_done=on_done,
    )
    return stream_response(answer.events())
