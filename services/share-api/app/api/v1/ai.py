"""IA para usuarios internos: búsqueda semántica y preguntas con citas sobre los documentos."""

import json
import uuid
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response
from fastapi import status as http_status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.ai import usage as ai_usage
from app.ai.agent import AgentRun, ChatContext
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
from app.core.errors import DomainError, NotFoundError
from app.db.models import AiConversation, AiMessage
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


# ---------------------------------------------------------------------- asistente (agente)
class ChatContextIn(BaseModel):
    path: str | None = Field(default=None, max_length=200)
    document_id: str | None = Field(default=None, max_length=100)
    library_id: str | None = Field(default=None, max_length=40)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    context: ChatContextIn | None = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    updated_at: datetime


class MessageOut(BaseModel):
    id: int
    role: str
    display: dict[str, Any]
    created_at: datetime


class ConversationDetail(ConversationOut):
    messages: list[MessageOut]


class ProposalOutcome(BaseModel):
    status: str = Field(pattern="^(confirmed|dismissed|failed)$")
    summary: str = Field(max_length=500)


def _own_conversation(db: Any, user_id: uuid.UUID, conversation_id: uuid.UUID) -> AiConversation:
    conversation: AiConversation | None = db.get(AiConversation, conversation_id)
    if conversation is None or conversation.user_id != user_id:
        raise NotFoundError("Conversación no encontrada")
    return conversation


@router.post("/chat", response_class=StreamingResponse)
def chat(
    body: ChatRequest,
    user: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    components: ComponentsDep,
    ctx: ContextDep,
) -> StreamingResponse:
    """Asistente con herramientas. SSE: conversation, text, citation, block_end, thinking, step,
    proposal, error, done. Las acciones llegan como propuestas que el usuario confirma."""
    if not settings.ai_enabled or components.llm is None:
        raise AiUnavailableError()
    ai_usage.ensure_budget(db, user.id, settings.ai_daily_token_budget)
    if body.conversation_id:
        _own_conversation(db, user.id, body.conversation_id)
    context = body.context or ChatContextIn()
    run = AgentRun(
        settings=settings,
        components=components,
        user_id=user.id,
        ctx=ctx,
        message=body.message,
        conversation_id=body.conversation_id,
        context=ChatContext(
            path=context.path, document_id=context.document_id, library_id=context.library_id
        ),
    )
    return stream_response(run.events())


@router.get("/conversations", response_model=list[ConversationOut])
def conversations(user: CurrentUserDep, db: DbDep) -> list[ConversationOut]:
    rows = db.scalars(
        select(AiConversation)
        .where(AiConversation.user_id == user.id)
        .order_by(AiConversation.updated_at.desc())
        .limit(100)
    )
    return [ConversationOut(id=r.id, title=r.title, updated_at=r.updated_at) for r in rows]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def conversation(conversation_id: uuid.UUID, user: CurrentUserDep, db: DbDep) -> ConversationDetail:
    conv = _own_conversation(db, user.id, conversation_id)
    rows = db.scalars(
        select(AiMessage)
        .where(AiMessage.conversation_id == conv.id, AiMessage.display.is_not(None))
        .order_by(AiMessage.id)
    )
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        updated_at=conv.updated_at,
        messages=[
            MessageOut(id=m.id, role=m.role, display=m.display or {}, created_at=m.created_at)
            for m in rows
        ],
    )


@router.delete("/conversations/{conversation_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: uuid.UUID, user: CurrentUserDep, db: DbDep) -> Response:
    conv = _own_conversation(db, user.id, conversation_id)
    db.execute(delete(AiConversation).where(AiConversation.id == conv.id))
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.post(
    "/conversations/{conversation_id}/proposals/{proposal_id}",
    status_code=http_status.HTTP_204_NO_CONTENT,
)
def proposal_outcome(
    conversation_id: uuid.UUID,
    proposal_id: str,
    body: ProposalOutcome,
    user: CurrentUserDep,
    db: DbDep,
    ctx: ContextDep,
) -> Response:
    """Registra qué hizo el usuario con una propuesta; el asistente lo sabrá en el próximo turno.
    La acción en sí ya quedó auditada por su endpoint (por ejemplo, SHARE_CREATED)."""
    conv = _own_conversation(db, user.id, conversation_id)
    for message in db.scalars(
        select(AiMessage).where(
            AiMessage.conversation_id == conv.id, AiMessage.display.is_not(None)
        )
    ):
        proposals = (message.display or {}).get("proposals") or []
        if any(p.get("id") == proposal_id for p in proposals):
            message.display = {
                **(message.display or {}),
                "proposals": [
                    {**p, "status": body.status} if p.get("id") == proposal_id else p
                    for p in proposals
                ],
            }
    verb = {"confirmed": "confirmó", "dismissed": "descartó", "failed": "intentó sin éxito"}
    conv.pending_notes = [
        *(conv.pending_notes or []),
        f"el usuario {verb[body.status]} la propuesta {proposal_id[:12]}: {body.summary}",
    ]
    if body.status == "confirmed":
        audit_service.record(
            db,
            event_type=AuditEventType.AI_ACTION_CONFIRMED,
            actor_type=ActorType.USER,
            actor_id=user.id,
            ctx=ctx,
            details={"proposal_id": proposal_id[:12], "summary": body.summary[:300]},
        )
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
