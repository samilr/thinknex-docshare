from __future__ import annotations

import hashlib
import io
import uuid
from datetime import UTC, datetime

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.adapters.document_source import (
    SourceDocument,
    SourceFolder,
    SourceLibrary,
    SourcePage,
    SourceVersion,
    UploadedFile,
)
from app.core.errors import ConflictError, NameConflictError, NotFoundError, ValidationFailedError
from app.domain.enums import Classification
from app.sensitivity.llm_classifier import LlmAssessment


def make_pdf(*lines: str) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4, invariant=1)
    y = 800
    for line in lines:
        c.drawString(72, y, line)
        y -= 18
    c.save()
    return buffer.getvalue()


class FakeDocumentSource:
    """DMS en memoria con la misma semántica que document-api (bibliotecas, carpetas, versiones)."""

    def __init__(self) -> None:
        self.docs: dict[str, tuple[SourceDocument, bytes]] = {}
        self.deleted: dict[str, tuple[SourceDocument, bytes]] = {}
        self._versions: dict[str, list[tuple[SourceVersion, bytes]]] = {}
        self._libraries = {
            "operaciones": "Operaciones",
            "legal": "Legal",
            "comercial": "Comercial",
        }
        self._folders: dict[str, SourceFolder] = {}

    # ------------------------------------------------------------------ helpers de test
    def add(
        self,
        doc_id: str,
        classification: Classification,
        *lines: str,
        library: str = "operaciones",
        folder_id: str | None = None,
    ) -> None:
        content = make_pdf(*lines)
        meta = SourceDocument(
            id=doc_id,
            title=f"Documento {doc_id}",
            mime_type="application/pdf",
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
            version=1,
            classification=classification,
            owner="owner@thinknex.example",
            filename=f"{doc_id}.pdf",
            library_id=library,
            folder_id=folder_id,
            created_by="owner@thinknex.example",
            updated_at=datetime.now(UTC),
        )
        self._store(meta, content, comment="Versión inicial", actor="owner@thinknex.example")

    def _store(self, meta: SourceDocument, content: bytes, comment: str, actor: str) -> None:
        version = SourceVersion(
            version=meta.version,
            sha256=meta.sha256,
            size_bytes=len(content),
            comment=comment,
            created_by=actor,
            created_at=datetime.now(UTC),
        )
        self.docs[meta.id] = (meta, content)
        self._versions.setdefault(meta.id, []).append((version, content))

    # ------------------------------------------------------------------ puerto DocumentSource
    def list(
        self,
        *,
        q: str | None,
        limit: int,
        offset: int,
        library_id: str | None = None,
        folder_id: str | None = None,
    ) -> SourcePage:
        items = [m for m, _ in self.docs.values()]
        if library_id:
            items = [m for m in items if m.library_id == library_id]
            if not q:
                items = [m for m in items if m.folder_id == folder_id]
        if q:
            items = [m for m in items if q.casefold() in (m.title + m.filename).casefold()]
        return SourcePage(
            items=items[offset : offset + limit], total=len(items), limit=limit, offset=offset
        )

    def get_metadata(self, doc_id: str) -> SourceDocument:
        if doc_id not in self.docs:
            raise NotFoundError("Documento no encontrado en el sistema documental")
        return self.docs[doc_id][0]

    def get_content(self, doc_id: str, version: int | None = None) -> bytes:
        meta = self.get_metadata(doc_id)
        wanted = version or meta.version
        return next(data for v, data in self._versions[doc_id] if v.version == wanted)

    def versions(self, doc_id: str) -> list[SourceVersion]:
        self.get_metadata(doc_id)
        return [v for v, _ in reversed(self._versions[doc_id])]

    def libraries(self) -> list[SourceLibrary]:
        return [
            SourceLibrary(
                id=lib_id,
                name=name,
                description="",
                document_count=sum(1 for m, _ in self.docs.values() if m.library_id == lib_id),
            )
            for lib_id, name in self._libraries.items()
        ]

    def folders(self, library_id: str, parent_id: str | None) -> list[SourceFolder]:
        return [
            f
            for f in self._folders.values()
            if f.library_id == library_id and f.parent_id == parent_id
        ]

    def folder_path(self, folder_id: str) -> list[SourceFolder]:
        path: list[SourceFolder] = []
        current = self._folders.get(folder_id)
        if current is None:
            raise NotFoundError("Carpeta no encontrada")
        while current is not None:
            path.append(current)
            current = self._folders.get(current.parent_id) if current.parent_id else None
        return list(reversed(path))

    def create_folder(
        self, *, library_id: str, parent_id: str | None, name: str, actor: str
    ) -> SourceFolder:
        if any(f.name.casefold() == name.casefold() for f in self.folders(library_id, parent_id)):
            raise ConflictError("Ya existe una carpeta con ese nombre")
        folder = SourceFolder(
            id=str(uuid.uuid4()),
            library_id=library_id,
            parent_id=parent_id,
            name=name,
            created_by=actor,
            created_at=datetime.now(UTC),
        )
        self._folders[folder.id] = folder
        return folder

    def upload(
        self,
        *,
        file: UploadedFile,
        library_id: str,
        folder_id: str | None,
        classification: Classification,
        title: str | None,
        actor: str,
    ) -> SourceDocument:
        if not file.data.startswith(b"%PDF-"):
            raise ValidationFailedError("El contenido del archivo no corresponde a su extensión")
        for meta, _ in self.docs.values():
            if (
                meta.library_id == library_id
                and meta.folder_id == folder_id
                and meta.filename.casefold() == file.filename.casefold()
            ):
                raise NameConflictError(
                    "Ya existe un archivo con ese nombre en esta ubicación", document_id=meta.id
                )
        meta = SourceDocument(
            id=f"doc-{uuid.uuid4().hex[:8]}",
            title=title or file.filename.rsplit(".", 1)[0],
            mime_type="application/pdf",
            size_bytes=len(file.data),
            sha256=hashlib.sha256(file.data).hexdigest(),
            version=1,
            classification=classification,
            owner=actor,
            filename=file.filename,
            library_id=library_id,
            folder_id=folder_id,
            created_by=actor,
            updated_at=datetime.now(UTC),
        )
        self._store(meta, file.data, comment="", actor=actor)
        return meta

    def upload_version(
        self, doc_id: str, *, file: UploadedFile, comment: str, actor: str
    ) -> SourceDocument:
        current = self.get_metadata(doc_id)
        meta = current.model_copy(
            update={
                "version": current.version + 1,
                "sha256": hashlib.sha256(file.data).hexdigest(),
                "size_bytes": len(file.data),
                "updated_at": datetime.now(UTC),
            }
        )
        self._store(meta, file.data, comment=comment, actor=actor)
        return meta

    def update(
        self,
        doc_id: str,
        *,
        name: str | None,
        classification: Classification | None,
        actor: str,
    ) -> SourceDocument:
        current = self.get_metadata(doc_id)
        changes: dict[str, object] = {}
        if name is not None:
            stem = name.strip().strip(".")
            if not stem or "/" in stem:
                raise ValidationFailedError("Nombre inválido")
            filename = f"{stem}.{current.filename.rsplit('.', 1)[-1]}"
            for meta, _ in self.docs.values():
                if (
                    meta.id != doc_id
                    and meta.library_id == current.library_id
                    and meta.folder_id == current.folder_id
                    and meta.filename.casefold() == filename.casefold()
                ):
                    raise NameConflictError(
                        "Ya existe un archivo con ese nombre en esta ubicación", document_id=meta.id
                    )
            changes.update(title=stem, filename=filename)
        if classification is not None:
            changes["classification"] = classification
        updated = current.model_copy(update=changes)
        self.docs[doc_id] = (updated, self.docs[doc_id][1])
        return updated

    def delete(self, doc_id: str, *, actor: str) -> None:
        self.get_metadata(doc_id)
        self.deleted[doc_id] = self.docs.pop(doc_id)

    def ping(self) -> bool:
        return True


class FakeClassifier:
    model = "fake-llm"

    def __init__(self, assessment: LlmAssessment | None) -> None:
        self.assessment = assessment
        self.received: list[str] = []

    def classify(self, *, title: str, redacted_text: str) -> LlmAssessment | None:
        self.received.append(redacted_text)
        return self.assessment


class FakeLlm:
    """Simula a Claude: responde citando el primer bloque del primer search_result recibido."""

    model = "fake-llm"

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.tool_script: list[object] = []

    def stream(self, *, model, system, messages, max_tokens=2000):  # type: ignore[no-untyped-def]
        from app.ai.llm import BlockEnd, Citation, Done, TextDelta, Usage

        self.calls.append({"model": model, "system": system, "messages": messages})
        results = [
            b
            for b in messages[-1]["content"]
            if isinstance(b, dict) and b["type"] == "search_result"
        ]
        if not results:
            yield TextDelta("No encontré esto en los documentos disponibles.")
        else:
            first = results[0]["content"][0]["text"]
            yield TextDelta("Según los documentos: ")
            yield TextDelta(first[:80])
            yield Citation(0, 0, 1, first)
            yield BlockEnd()
        yield Done(Usage(model=model, input_tokens=120, output_tokens=30))

    def tool_turn(self, *, model, system, messages, tools, max_tokens=4000):  # type: ignore[no-untyped-def]
        from app.ai.llm import ToolTurn, Usage

        self.calls.append({"model": model, "system": system, "messages": messages, "tools": tools})
        step = self.tool_script.pop(0) if self.tool_script else {"text": "Listo."}
        assert isinstance(step, dict)
        if "tool" in step:
            call = {
                "type": "tool_use",
                "id": f"tu_{len(self.calls)}",
                "name": step["tool"],
                "input": step["input"],
            }
            return ToolTurn(
                content=[call],
                stop_reason="tool_use",
                usage=Usage(model=model, input_tokens=50, output_tokens=10),
                tool_calls=[call],
            )
        block = {"type": "text", "text": step["text"]}
        return ToolTurn(
            content=[block],
            stop_reason="end_turn",
            usage=Usage(model=model, input_tokens=50, output_tokens=10),
            text=step["text"],
        )


def _search_result_count(messages):  # type: ignore[no-untyped-def]
    count = 0
    for m in messages:
        if m["role"] != "user" or not isinstance(m["content"], list):
            continue
        for b in m["content"]:
            if b.get("type") == "search_result":
                count += 1
            elif b.get("type") == "tool_result" and isinstance(b.get("content"), list):
                count += sum(1 for i in b["content"] if i.get("type") == "search_result")
    return count


def _fake_stream_turn(self, *, model, system, messages, tools, max_tokens=4000):  # type: ignore[no-untyped-def]
    """Turnos guionados: {"tool": nombre, "input": {...}} o {"text": "...", "cite": bool}."""
    from app.ai.llm import BlockEnd, Citation, TextDelta, ToolStart, TurnEnd, Usage

    self.calls.append(
        {"model": model, "system": system, "messages": list(messages), "tools": tools}
    )
    step = self.tool_script.pop(0) if self.tool_script else {"text": "Listo."}
    usage = Usage(model=model, input_tokens=80, output_tokens=20)
    if "tool" in step:
        call = {
            "type": "tool_use",
            "id": f"tu_{len(self.calls)}",
            "name": step["tool"],
            "input": step["input"],
        }
        yield ToolStart(step["tool"])
        yield TurnEnd(content=[call], stop_reason="tool_use", usage=usage)
        return
    yield TextDelta(step["text"])
    total = _search_result_count(messages)
    if step.get("cite") and total:
        yield Citation(total - 1, 0, 1, "texto citado")
    yield BlockEnd()
    yield TurnEnd(
        content=[{"type": "text", "text": step["text"]}], stop_reason="end_turn", usage=usage
    )


FakeLlm.stream_turn = _fake_stream_turn  # type: ignore[attr-defined]
