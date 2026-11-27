"""Búsqueda y preguntas con citas: permisos, alcance, redacción, auditoría y presupuesto."""

import json
import uuid
from collections.abc import Iterator

import pytest

from app.ai.index_service import IndexService
from app.core.config import Settings
from app.db.models import AiUsage
from tests.helpers import FakeLlm, make_pdf
from tests.integration.conftest import Api

pytestmark = pytest.mark.integration
WORD = f"zorzal{uuid.uuid4().hex[:4]}"


@pytest.fixture
def llm(api: Api) -> Iterator[FakeLlm]:
    fake = FakeLlm()
    api.components.llm = fake
    yield fake
    api.components.llm = None


_INDEXED: dict[str, str] = {}


@pytest.fixture
def indexed(api: Api, settings: Settings) -> dict[str, str]:
    if _INDEXED:
        return _INDEXED
    ana = api.headers("ana@thinknex.example")
    ids = _INDEXED
    for key, library, lines in (
        (
            "viajes",
            "operaciones",
            ["Politica de viajes", f"Viaticos diarios {WORD} de 45000 pesos"],
        ),
        ("cliente", "comercial", [f"Ficha {WORD} cliente", "RUT 18.456.789-K del titular"]),
    ):
        r = api.client.post(
            "/api/v1/library/documents",
            data={"library_id": library, "classification": "INTERNAL"},
            files={"file": (f"{key}-{WORD}.pdf", make_pdf(*lines), "application/pdf")},
            headers=ana,
        )
        ids[key] = r.json()["document"]["id"]
    with api.components.session_factory() as db:
        service = IndexService(db, settings, api.components.source, api.components.embedder)
        while service.run_pending(limit=50):
            pass
    return ids


def _sse(text: str) -> list[tuple[str, dict]]:  # type: ignore[type-arg]
    events = []
    for chunk in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in chunk.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_search_is_hybrid_and_scoped(api: Api, indexed: dict[str, str]) -> None:
    ana = api.headers("ana@thinknex.example")
    hits = api.client.get("/api/v1/ai/search", params={"q": f"viaticos {WORD}"}, headers=ana)
    assert hits.status_code == 200, hits.text
    assert hits.json()[0]["document_id"] == indexed["viajes"]
    scoped = api.client.get(
        "/api/v1/ai/search", params={"q": WORD, "library_id": "comercial"}, headers=ana
    ).json()
    assert {h["document_id"] for h in scoped} == {indexed["cliente"]}
    carla = api.headers("carla@thinknex.example")
    assert api.client.get("/api/v1/ai/search", params={"q": WORD}, headers=carla).status_code == 403


def test_ask_streams_answer_with_citations_redacts_and_audits(
    api: Api, indexed: dict[str, str], llm: FakeLlm
) -> None:
    ana = api.headers("ana@thinknex.example")
    r = api.client.post(
        "/api/v1/ai/ask",
        json={
            "question": f"¿Qué dice la ficha {WORD} del cliente 11.111.111-1?",
            "document_ids": [indexed["cliente"]],
        },
        headers=ana,
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _sse(r.text)
    names = [name for name, _ in events]
    assert names[0] == "sources" and names[-1] == "done" and "citation" in names
    sources = events[0][1]["sources"]
    assert [s["document_id"] for s in sources] == [indexed["cliente"]]
    citation = next(data for name, data in events if name == "citation")
    assert citation["n"] == 1 and citation["document_id"] == indexed["cliente"]

    sent = json.dumps(llm.calls[-1]["messages"], ensure_ascii=False)
    assert "18.456.789-K" not in sent and "[RUT]" in sent, "el LLM recibe el RUT redactado"

    audit = api.audit(event_type="AI_QUERY")[0]
    assert "11.111.111-1" not in audit["metadata"]["question"]  # type: ignore[index]
    assert audit["metadata"]["documents"] == [indexed["cliente"]]  # type: ignore[index]
    with api.components.session_factory() as db:
        assert db.query(AiUsage).filter(AiUsage.feature == "ask").count() >= 1


def test_ask_without_llm_or_over_budget(api: Api, indexed: dict[str, str], llm: FakeLlm) -> None:
    ana = api.headers("ana@thinknex.example")
    body = {"question": f"viaticos {WORD}"}
    api.components.llm = None
    assert api.client.post("/api/v1/ai/ask", json=body, headers=ana).status_code == 503
    api.components.llm = llm
    me = api.client.get("/api/v1/auth/me", headers=ana).json()
    with api.components.session_factory() as db, db.begin():
        db.add(AiUsage(user_id=uuid.UUID(me["id"]), feature="test", model="x", input_tokens=10**7))
    try:
        assert api.client.post("/api/v1/ai/ask", json=body, headers=ana).status_code == 429
    finally:
        with api.components.session_factory() as db, db.begin():
            db.query(AiUsage).filter(AiUsage.feature == "test").delete()
