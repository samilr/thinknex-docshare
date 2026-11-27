"""Herramientas del asistente. Se ejecutan con la identidad y los permisos de quien conversa.

- Las de lectura (buscar, leer, listar, revisar política, auditoría) corren solas.
- Las que cambian algo (``proponer_*``) NUNCA ejecutan: devuelven una propuesta que el usuario
  confirma en la interfaz, que entonces llama al endpoint normal (política, OTP y auditoría
  incluidas).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import index_service as ai_index
from app.ai.answer_service import blocks_for, page_label
from app.ai.retrieval import Hit, Scope, search
from app.container import Components
from app.core.config import Settings
from app.core.errors import DomainError, ForbiddenError, NotFoundError
from app.db.models import AiChunk, AiIndex, User
from app.domain.enums import (
    ActorType,
    Audience,
    AuditEventType,
    Channel,
    Permission,
    Role,
    ShareStatus,
)
from app.schemas import RecipientIn
from app.services import audit_service
from app.services.context import RequestContext
from app.services.share_service import ShareService

SOURCE_SCHEME = "thinknex"
_LIBRARY = (Role.SHARER, Role.ADMIN)
_OVERSIGHT = (Role.ADMIN, Role.AUDITOR)


def encode_source(hit: Hit) -> str:
    query = urlencode(
        {
            "lib": hit.library_id or "",
            "folder": hit.folder_id or "",
            "p": f"{hit.page_from}-{hit.page_to}",
        }
    )
    return f"{SOURCE_SCHEME}://doc/{hit.source_document_id}?{query}"


def decode_source(source: str, title: str) -> dict[str, Any]:
    """Metadata de una fuente a partir del ``source`` de un bloque search_result."""
    parsed = urlparse(source)
    params = {k: v[0] for k, v in parse_qs(parsed.query, keep_blank_values=True).items()}
    page_from, _, page_to = params.get("p", "1-1").partition("-")
    base_title = title.rsplit(" (p", 1)[0]
    return {
        "document_id": parsed.path.lstrip("/"),
        "title": base_title,
        "library_id": params.get("lib") or None,
        "folder_id": params.get("folder") or None,
        "page_from": int(page_from or 1),
        "page_to": int(page_to or page_from or 1),
    }


def to_search_results(hits: list[Hit], redact_pii: bool) -> list[dict[str, Any]]:
    return [
        {
            "type": "search_result",
            "source": encode_source(hit),
            "title": f"{hit.title} ({page_label(hit)})",
            "content": [{"type": "text", "text": b} for b in blocks_for(hit, redact_pii)],
            "citations": {"enabled": True},
        }
        for hit in hits
    ]


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


_STR = {"type": "string"}
TOOLS: dict[str, dict[str, Any]] = {
    "buscar_documentos": {
        "roles": _LIBRARY,
        "label": "Buscó en los documentos",
        "description": (
            "Busca fragmentos relevantes en los documentos que el usuario puede ver (búsqueda "
            "semántica y por texto). Úsala para responder preguntas sobre el contenido. Devuelve "
            "resultados citables."
        ),
        "input_schema": _schema(
            {
                "consulta": {**_STR, "description": "Qué buscar, en lenguaje natural"},
                "biblioteca_id": {**_STR, "description": "Opcional: limita a una biblioteca"},
                "documento_ids": {
                    "type": "array",
                    "items": _STR,
                    "description": "Opcional: limita a estos documentos",
                },
            },
            ["consulta"],
        ),
    },
    "leer_documento": {
        "roles": _LIBRARY,
        "label": "Leyó el documento",
        "description": (
            "Devuelve el contenido de un documento (sus primeros fragmentos, en orden) para "
            "resumirlo o analizarlo completo. Resultados citables."
        ),
        "input_schema": _schema({"documento_id": _STR}, ["documento_id"]),
    },
    "listar_documentos": {
        "roles": _LIBRARY,
        "label": "Revisó la biblioteca",
        "description": (
            "Lista documentos de la biblioteca con su id, clasificación y versión. Úsala para "
            "encontrar un documento por nombre o ver qué hay en una biblioteca."
        ),
        "input_schema": _schema(
            {
                "consulta": {**_STR, "description": "Opcional: parte del nombre"},
                "biblioteca_id": {**_STR, "description": "Opcional"},
            }
        ),
    },
    "ver_documento": {
        "roles": _LIBRARY,
        "label": "Consultó el documento",
        "description": "Ficha de un documento: metadata, versiones y envíos activos.",
        "input_schema": _schema({"documento_id": _STR}, ["documento_id"]),
    },
    "listar_envios": {
        "roles": (Role.SHARER, Role.ADMIN, Role.AUDITOR),
        "label": "Revisó los envíos",
        "description": (
            "Lista envíos (documentos compartidos) visibles para el usuario: destinatario, medio, "
            "permiso, estado y vencimiento."
        ),
        "input_schema": _schema(
            {
                "estado": {
                    "type": "string",
                    "enum": ["ACTIVE", "REVOKED", "EXPIRED", "LOCKED", "EXHAUSTED"],
                },
                "documento_id": _STR,
            }
        ),
    },
    "revisar_politica": {
        "roles": _LIBRARY,
        "label": "Revisó la política de compartición",
        "description": (
            "Evalúa si un documento puede compartirse con un destinatario según la política "
            "(datos sensibles, clasificación, reglas). No comparte nada."
        ),
        "input_schema": _schema(
            {
                "documento_id": _STR,
                "audiencia": {"type": "string", "enum": ["SPECIFIC", "ANYONE"]},
                "destinatario_email": _STR,
                "destinatario_telefono": _STR,
                "canal": {"type": "string", "enum": ["LINK", "EMAIL", "WHATSAPP", "SMS"]},
            },
            ["documento_id", "audiencia"],
        ),
    },
    "consultar_auditoria": {
        "roles": _OVERSIGHT,
        "label": "Consultó la auditoría",
        "description": (
            "Eventos recientes de la auditoría (quién hizo qué, cuándo y por qué medio). Tipos "
            "útiles: SHARE_CREATED, SHARE_BLOCKED, ACCESS_DENIED, DOCUMENT_ACCESSED, OTP_FAILED, "
            "SHARE_REVOKED, POLICY_UPDATED, USER_LOGIN_FAILED."
        ),
        "input_schema": _schema(
            {
                "evento": _STR,
                "documento_id": _STR,
                "limite": {"type": "integer", "minimum": 1, "maximum": 30},
            }
        ),
    },
    "proponer_envio": {
        "roles": _LIBRARY,
        "label": "Preparó un envío para confirmar",
        "description": (
            "Prepara compartir un documento. NO lo comparte: el usuario revisa la propuesta, pasa "
            "la revisión de seguridad y confirma. Para 'cualquiera con el enlace' usa canal LINK y "
            "audiencia ANYONE sin destinatario."
        ),
        "input_schema": _schema(
            {
                "documento_id": _STR,
                "canal": {"type": "string", "enum": ["LINK", "EMAIL", "WHATSAPP", "SMS"]},
                "audiencia": {"type": "string", "enum": ["SPECIFIC", "ANYONE"]},
                "permiso": {"type": "string", "enum": ["VIEW", "DOWNLOAD", "EDIT"]},
                "motivo": _STR,
                "destinatario_nombre": _STR,
                "destinatario_email": _STR,
                "destinatario_telefono": _STR,
                "vencimiento_horas": {"type": "integer", "minimum": 1, "maximum": 168},
                "accesos": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            ["documento_id", "canal", "audiencia", "permiso", "motivo"],
        ),
    },
    "proponer_revocacion": {
        "roles": _LIBRARY,
        "label": "Preparó una revocación para confirmar",
        "description": "Prepara revocar un envío. NO lo revoca: el usuario confirma.",
        "input_schema": _schema({"envio_id": _STR, "motivo": _STR}, ["envio_id"]),
    },
    "proponer_cambio_acceso": {
        "roles": _LIBRARY,
        "label": "Preparó un cambio de acceso para confirmar",
        "description": (
            "Prepara cambiar el acceso de un envío (permiso, marca de agua, vencimiento o "
            "accesos). NO lo aplica: el usuario confirma."
        ),
        "input_schema": _schema(
            {
                "envio_id": _STR,
                "permiso": {"type": "string", "enum": ["VIEW", "DOWNLOAD", "EDIT"]},
                "marca_agua": {"type": "boolean"},
                "vencimiento_horas": {"type": "integer", "minimum": 1, "maximum": 168},
                "accesos": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            ["envio_id"],
        ),
    },
}


def tools_for(user: User) -> list[dict[str, Any]]:
    """Definiciones para la API, solo las que el rol permite (orden estable para el caché)."""
    return [
        {"name": name, "description": spec["description"], "input_schema": spec["input_schema"]}
        for name, spec in TOOLS.items()
        if user.has_any(*(r.value for r in spec["roles"]))
    ]


@dataclass
class ToolOutput:
    content: str | list[dict[str, Any]]
    label: str
    is_error: bool = False
    proposal: dict[str, Any] | None = None
    sources: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ToolBox:
    db: Session
    settings: Settings
    components: Components
    user: User
    ctx: RequestContext

    @property
    def shares(self) -> ShareService:
        c = self.components
        return ShareService(self.db, self.settings, c.source, c.storage, c.channels, c.checker)

    def run(self, name: str, args: dict[str, Any]) -> ToolOutput:
        spec = TOOLS.get(name)
        if spec is None or not self.user.has_any(*(r.value for r in spec["roles"])):
            return ToolOutput(f"Herramienta no disponible: {name}", name, is_error=True)
        try:
            output: ToolOutput = getattr(self, f"_{name}")(**args)
        except DomainError as exc:
            return ToolOutput(f"Error: {exc.detail or exc.title}", spec["label"], is_error=True)
        except (TypeError, ValueError) as exc:
            return ToolOutput(f"Parámetros inválidos: {exc}", spec["label"], is_error=True)
        output.label = output.label or spec["label"]
        return output

    # ------------------------------------------------------------------ lectura
    def _results(self, hits: list[Hit], label: str) -> ToolOutput:
        if not hits:
            return ToolOutput("Sin resultados en los documentos accesibles.", label)
        blocks = to_search_results(hits, self.settings.ai_redact_pii)
        sources = [decode_source(b["source"], b["title"]) for b in blocks]
        return ToolOutput(blocks, label, sources=sources)

    def _buscar_documentos(
        self,
        consulta: str,
        biblioteca_id: str | None = None,
        documento_ids: list[str] | None = None,
    ) -> ToolOutput:
        scope = Scope(library_id=biblioteca_id, document_ids=tuple(documento_ids or ()))
        hits = search(self.db, self.components.embedder, consulta, scope, limit=8)
        return self._results(hits, f"Buscó «{consulta[:60]}»")

    def _leer_documento(self, documento_id: str) -> ToolOutput:
        row = ai_index.current_status(self.db, documento_id)
        if row is None:
            raise NotFoundError("Documento no encontrado o aún no indexado")
        if row.status != "INDEXED":
            return ToolOutput(
                f"El documento no tiene contenido disponible para la IA ({row.status}: "
                f"{row.error or 'sin texto'}).",
                "Leyó el documento",
            )
        chunks = self.db.scalars(
            select(AiChunk)
            .where(AiChunk.index_id == row.id)
            .order_by(AiChunk.chunk_index)
            .limit(12)
        ).all()
        hits = [
            Hit(
                chunk_id=c.id,
                source_document_id=row.source_document_id,
                title=row.title,
                filename=row.filename,
                library_id=row.library_id,
                folder_id=row.folder_id,
                classification=row.classification,
                version=row.version,
                page_from=c.page_from,
                page_to=c.page_to,
                text=c.text,
            )
            for c in chunks
        ]
        return self._results(hits, f"Leyó «{row.title[:60]}»")

    def _listar_documentos(
        self, consulta: str | None = None, biblioteca_id: str | None = None
    ) -> ToolOutput:
        page = self.components.source.list(
            q=consulta or None, limit=30, offset=0, library_id=biblioteca_id
        )
        libraries = {lib.id: lib.name for lib in self.components.source.libraries()}
        if not page.items:
            return ToolOutput("No hay documentos que coincidan.", "Revisó la biblioteca")
        lines = [
            f"- {d.id} · «{d.title}» · {d.classification.value} · v{d.version} · "
            f"{libraries.get(d.library_id or '', d.library_id)}"
            for d in page.items
        ]
        return ToolOutput(
            f"{page.total} documento(s):\n" + "\n".join(lines), "Revisó la biblioteca"
        )

    def _ver_documento(self, documento_id: str) -> ToolOutput:
        meta = self.components.source.get_metadata(documento_id)
        versions = self.components.source.versions(documento_id)
        shares = self.shares.search(
            self.user,
            scope="all" if self.user.has_any(Role.ADMIN) else "mine",
            status=ShareStatus.ACTIVE,
            channel=None,
            document_id=documento_id,
            limit=50,
            offset=0,
        )
        row = ai_index.current_status(self.db, documento_id)
        summary = f"\nResumen: {row.summary}" if row and row.summary else ""
        return ToolOutput(
            f"{meta.id} · «{meta.title}» ({meta.filename})\nClasificación: "
            f"{meta.classification.value} · versión {meta.version} ({len(versions)} en total) · "
            f"responsable {meta.owner}\nEnvíos activos visibles: {shares.total}{summary}",
            f"Consultó «{meta.title[:60]}»",
        )

    def _listar_envios(
        self, estado: str | None = None, documento_id: str | None = None
    ) -> ToolOutput:
        page = self.shares.search(
            self.user,
            scope="all" if self.user.has_any(Role.ADMIN, Role.AUDITOR) else "mine",
            status=ShareStatus(estado) if estado else None,
            channel=None,
            document_id=documento_id,
            limit=25,
            offset=0,
        )
        if not page.items:
            return ToolOutput("No hay envíos que coincidan.", "Revisó los envíos")
        lines = []
        for s in page.items:
            who = f"{s.recipient.name} ({s.recipient.contact})" if s.recipient else "cualquiera"
            lines.append(
                f"- envío {s.id} · «{s.document.title}» ({s.document.source_id}) · para {who} · "
                f"{s.channel.value} · permiso {s.permission.value} · {s.status.value} · "
                f"{s.access_count}/{s.max_accesses} accesos · "
                f"vence {s.expires_at:%Y-%m-%d %H:%M} UTC · compartido por {s.shared_by}"
            )
        return ToolOutput(f"{page.total} envío(s):\n" + "\n".join(lines), "Revisó los envíos")

    def _revisar_politica(
        self,
        documento_id: str,
        audiencia: str,
        destinatario_email: str | None = None,
        destinatario_telefono: str | None = None,
        canal: str | None = None,
    ) -> ToolOutput:
        recipient = None
        if audiencia == "SPECIFIC":
            recipient = RecipientIn(
                name="Destinatario", email=destinatario_email, phone=destinatario_telefono
            )
        report = self.shares.precheck(
            self.user,
            documento_id,
            recipient,
            Audience(audiencia),
            Channel(canal) if canal else None,
        ).report
        findings = ", ".join(f"{f.type} ({f.count})" for f in report.findings) or "ninguno"
        reasons = "\n".join(f"- {r}" for r in report.reasons) or "- (sin observaciones)"
        return ToolOutput(
            f"Decisión: {report.decision.value} (ALLOW=permitido, WARN=requiere confirmación, "
            f"BLOCK=bloqueado)\nClasificación: {report.classification.value}\n"
            f"Datos detectados: {findings}\nReglas aplicadas: "
            f"{', '.join(report.matched_rules) or 'ninguna'}\nMotivos:\n{reasons}",
            "Revisó la política de compartición",
        )

    def _consultar_auditoria(
        self, evento: str | None = None, documento_id: str | None = None, limite: int = 15
    ) -> ToolOutput:
        filters = audit_service.AuditFilters(
            event_type=AuditEventType(evento) if evento else None,
            source_document_id=documento_id,
        )
        rows, total = audit_service.query(self.db, filters, limit=min(limite, 30), offset=0)
        labels = audit_service.actor_labels(self.db, rows)
        if not rows:
            return ToolOutput("Sin eventos para ese filtro.", "Consultó la auditoría")
        lines = [
            f"- #{r.id} {r.occurred_at:%Y-%m-%d %H:%M} UTC · {r.event_type} · "
            f"{labels.get(r.actor_id or '', r.actor_type)} · {r.channel or '-'}"
            for r in rows
        ]
        return ToolOutput(
            f"{total} evento(s), recientes:\n" + "\n".join(lines), "Consultó la auditoría"
        )

    # ------------------------------------------------------------------ propuestas
    def _proposal(self, kind: str, data: dict[str, Any], summary: str, label: str) -> ToolOutput:
        proposal = {"id": uuid.uuid4().hex[:12], "kind": kind, "data": data, "summary": summary}
        audit_service.record(
            self.db,
            event_type=AuditEventType.AI_ACTION_PROPOSED,
            actor_type=ActorType.USER,
            actor_id=self.user.id,
            ctx=self.ctx,
            details={"proposal_id": proposal["id"], "kind": kind, "data": data},
        )
        return ToolOutput(
            f"Propuesta {proposal['id']} mostrada al usuario para que la revise y confirme. "
            "Todavía NO se ejecutó: no digas que se hizo.",
            label,
            proposal=proposal,
        )

    def _owned_share(self, envio_id: str) -> Any:
        share = self.shares.get(self.user, uuid.UUID(envio_id))
        if share.shared_by != self.user.email and not self.user.has_any(Role.ADMIN):
            raise ForbiddenError("Solo quien compartió o un ADMIN puede modificar este envío")
        if share.status not in (ShareStatus.ACTIVE, ShareStatus.EXHAUSTED):
            raise DomainError(f"El envío no está vigente ({share.status.value})")
        return share

    def _proponer_envio(
        self,
        documento_id: str,
        canal: str,
        audiencia: str,
        permiso: str,
        motivo: str,
        destinatario_nombre: str | None = None,
        destinatario_email: str | None = None,
        destinatario_telefono: str | None = None,
        vencimiento_horas: int | None = None,
        accesos: int | None = None,
    ) -> ToolOutput:
        meta = self.components.source.get_metadata(documento_id)
        Channel(canal), Audience(audiencia), Permission(permiso)  # validación temprana
        data = {
            "document_id": meta.id,
            "document_title": meta.title,
            "channel": canal,
            "audience": audiencia,
            "permission": permiso,
            "reason": motivo,
            "recipient": None
            if audiencia == "ANYONE"
            else {
                "name": destinatario_nombre or "",
                "email": destinatario_email,
                "phone": destinatario_telefono,
            },
            "expires_in_hours": vencimiento_horas,
            "max_accesses": accesos,
        }
        who = (
            "cualquiera con el enlace"
            if audiencia == "ANYONE"
            else (destinatario_nombre or destinatario_email or destinatario_telefono or "?")
        )
        return self._proposal(
            "share",
            data,
            f"Compartir «{meta.title}» con {who} por {canal} ({permiso})",
            "Preparó un envío para confirmar",
        )

    def _proponer_revocacion(self, envio_id: str, motivo: str | None = None) -> ToolOutput:
        share = self._owned_share(envio_id)
        who = share.recipient.name if share.recipient else "cualquiera con el enlace"
        return self._proposal(
            "revoke",
            {"share_id": str(share.id), "reason": motivo, "document_title": share.document.title},
            f"Revocar el envío de «{share.document.title}» a {who}",
            "Preparó una revocación para confirmar",
        )

    def _proponer_cambio_acceso(
        self,
        envio_id: str,
        permiso: str | None = None,
        marca_agua: bool | None = None,
        vencimiento_horas: int | None = None,
        accesos: int | None = None,
    ) -> ToolOutput:
        share = self._owned_share(envio_id)
        changes: dict[str, Any] = {}
        parts = []
        if permiso:
            changes["permission"] = Permission(permiso).value
            parts.append(f"permiso {permiso}")
        if marca_agua is not None:
            changes["watermark"] = marca_agua
            parts.append("con marca de agua" if marca_agua else "sin marca de agua")
        if vencimiento_horas:
            changes["expires_in_hours"] = vencimiento_horas
            parts.append(f"vence en {vencimiento_horas} h")
        if accesos:
            changes["max_accesses"] = accesos
            parts.append(f"{accesos} accesos")
        if not changes:
            raise DomainError("No se indicó ningún cambio")
        return self._proposal(
            "update_share",
            {"share_id": str(share.id), "changes": changes, "document_title": share.document.title},
            f"Cambiar el acceso de «{share.document.title}»: {', '.join(parts)}",
            "Preparó un cambio de acceso para confirmar",
        )


def index_title(db: Session, document_id: str) -> str | None:
    return db.scalar(
        select(AiIndex.title).where(
            AiIndex.source_document_id == document_id, AiIndex.is_current.is_(True)
        )
    )
