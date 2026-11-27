"""Asistente agéntico: herramientas con permisos, citas, propuestas, conversaciones y notas."""

import json
import uuid
from collections.abc import Iterator

import pytest

from tests.helpers import FakeLlm, make_pdf
from tests.integration.conftest import Api

pytestmark = pytest.mark.integration
WORD = f"alerce{uuid.uuid4().hex[:4]}"


@pytest.fixture
def llm(api: Api) -> Iterator[FakeLlm]:
    fake = FakeLlm()
    api.components.llm = fake
    yield fake
    api.components.llm = None


def _sse(text: str) -> list[tuple[str, dict]]:  # type: ignore[type-arg]
    out = []
    for chunk in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in chunk.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def _chat(
    api: Api, headers: dict[str, str], message: str, **extra: object
) -> list[tuple[str, dict]]:  # type: ignore[type-arg]
    r = api.client.post("/api/v1/ai/chat", json={"message": message, **extra}, headers=headers)
    assert r.status_code == 200, r.text
    return _sse(r.text)


def _doc(api: Api) -> str:
    r = api.client.post(
        "/api/v1/library/documents",
        data={"library_id": "operaciones", "classification": "INTERNAL"},
        files={
            "file": (
                f"manual-{WORD}.pdf",
                make_pdf("Manual de compras", f"Regla {WORD}: tres cotizaciones"),
                "application/pdf",
            )
        },
        headers=api.headers("ana@thinknex.example"),
    )
    doc_id: str = r.json()["document"]["id"]
    return doc_id


def test_agent_searches_cites_and_saves_conversation(api: Api, llm: FakeLlm) -> None:
    doc_id = _doc(api)
    ana = api.headers("ana@thinknex.example")
    llm.tool_script = [
        {
            "tool": "buscar_documentos",
            "input": {"consulta": f"regla {WORD} cotizaciones", "documento_ids": [doc_id]},
        },
        {"text": "Se requieren tres cotizaciones.", "cite": True},
    ]
    events = _chat(
        api,
        ana,
        "¿Cuántas cotizaciones pide el manual?",
        context={"path": "/documentos", "document_id": doc_id},
    )
    names = [n for n, _ in events]
    assert names[0] == "conversation" and names[-1] == "done"
    assert "step" in names and "citation" in names
    citation = next(d for n, d in events if n == "citation")
    assert citation["source"]["document_id"] == doc_id and citation["n"] == 1
    conv_id = events[0][1]["id"]

    first_call = json.dumps(llm.calls[0]["messages"], ensure_ascii=False)
    assert "Contexto de pantalla" in first_call and doc_id in first_call
    tool_names = {t["name"] for t in llm.calls[0]["tools"]}
    assert "buscar_documentos" in tool_names and "consultar_auditoria" not in tool_names

    listed = api.client.get("/api/v1/ai/conversations", headers=ana).json()
    assert listed[0]["id"] == conv_id
    detail = api.client.get(f"/api/v1/ai/conversations/{conv_id}", headers=ana).json()
    roles = [m["role"] for m in detail["messages"]]
    assert roles == ["user", "assistant"]
    answer = detail["messages"][1]["display"]
    assert answer["sources"][0]["document_id"] == doc_id and answer["steps"]

    # Segundo turno: recibe el historial (pregunta, uso de herramienta, resultado y respuesta).
    llm.tool_script = [{"text": "De nada."}]
    _chat(api, ana, "Gracias", conversation_id=conv_id)
    assert len(llm.calls[-1]["messages"]) == 5

    audit = api.audit(event_type="AI_QUERY")[0]
    assert audit["metadata"]["feature"] == "assistant"  # type: ignore[index]

    bruno = api.headers("bruno@thinknex.example")
    assert api.client.get(f"/api/v1/ai/conversations/{conv_id}", headers=bruno).status_code == 404
    assert api.client.delete(f"/api/v1/ai/conversations/{conv_id}", headers=ana).status_code == 204
    assert api.client.get(f"/api/v1/ai/conversations/{conv_id}", headers=ana).status_code == 404


def test_actions_are_only_proposals_and_outcome_is_noted(api: Api, llm: FakeLlm) -> None:
    share = api.share()
    ana = api.headers("ana@thinknex.example")
    llm.tool_script = [
        {
            "tool": "proponer_revocacion",
            "input": {"envio_id": share["id"], "motivo": "ya no aplica"},
        },
        {"text": "Dejé lista la revocación para que la confirmes."},
    ]
    events = _chat(api, ana, "Revoca el último envío")
    proposal = next(d for n, d in events if n == "proposal")
    assert proposal["kind"] == "revoke" and proposal["data"]["share_id"] == share["id"]
    detail = api.client.get(f"/api/v1/shares/{share['id']}", headers=ana).json()
    assert detail["status"] == "ACTIVE", "proponer no ejecuta"
    assert api.audit(event_type="AI_ACTION_PROPOSED")[0]["metadata"]["kind"] == "revoke"  # type: ignore[index]

    conv_id = events[0][1]["id"]
    r = api.client.post(
        f"/api/v1/ai/conversations/{conv_id}/proposals/{proposal['id']}",
        json={"status": "confirmed", "summary": "Envío revocado"},
        headers=ana,
    )
    assert r.status_code == 204
    shown = api.client.get(f"/api/v1/ai/conversations/{conv_id}", headers=ana).json()
    assert shown["messages"][1]["display"]["proposals"][0]["status"] == "confirmed"
    llm.tool_script = [{"text": "Perfecto."}]
    _chat(api, ana, "¿Listo?", conversation_id=conv_id)
    assert "[Nota del sistema: el usuario confirmó la propuesta" in json.dumps(
        llm.calls[-1]["messages"][-1], ensure_ascii=False
    )

    # Bruno no puede proponer sobre un envío de Ana: la herramienta devuelve error.
    llm.tool_script = [
        {"tool": "proponer_revocacion", "input": {"envio_id": share["id"]}},
        {"text": "No pude."},
    ]
    events = _chat(api, api.headers("bruno@thinknex.example"), "Revoca ese envío")
    step = next(d for n, d in events if n == "step")
    assert step["error"] is True
    assert not [d for n, d in events if n == "proposal"]


def test_auditor_gets_oversight_tools_only(api: Api, llm: FakeLlm) -> None:
    carla = api.headers("carla@thinknex.example")
    llm.tool_script = [
        {"tool": "buscar_documentos", "input": {"consulta": "x"}},
        {"tool": "consultar_auditoria", "input": {"evento": "SHARE_CREATED", "limite": 3}},
        {"text": "Resumen de auditoría."},
    ]
    events = _chat(api, carla, "¿Qué se compartió hoy?")
    steps = [d for n, d in events if n == "step"]
    assert steps[0]["error"] is True, "el auditor no busca en documentos"
    assert steps[1]["error"] is False
    names = {t["name"] for t in llm.calls[0]["tools"]}
    assert "consultar_auditoria" in names and "buscar_documentos" not in names
    tool_result = llm.calls[-1]["messages"][-1]["content"][0]["content"]
    assert "SHARE_CREATED" in tool_result


def test_chat_requires_llm(api: Api) -> None:
    r = api.client.post(
        "/api/v1/ai/chat", json={"message": "hola"}, headers=api.headers("ana@thinknex.example")
    )
    assert r.status_code == 503
