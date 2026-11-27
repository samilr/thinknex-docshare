"""Índice de IA: la biblioteca encola, la cola indexa y el detalle muestra el estado."""

import uuid

import pytest
from sqlalchemy import func, select

from app.ai.index_service import IndexService
from app.db.models import AiChunk, AiIndex
from tests.helpers import make_pdf
from tests.integration.conftest import Api

pytestmark = pytest.mark.integration


def _upload(api: Api, name: str, *lines: str, classification: str = "INTERNAL") -> str:
    r = api.client.post(
        "/api/v1/library/documents",
        data={"library_id": "operaciones", "classification": classification},
        files={"file": (name, make_pdf(*lines), "application/pdf")},
        headers=api.headers("ana@thinknex.example"),
    )
    assert r.status_code == 201, r.text
    doc_id: str = r.json()["document"]["id"]
    return doc_id


def _row(api: Api, doc_id: str) -> AiIndex | None:
    with api.components.session_factory() as db:
        return db.scalar(
            select(AiIndex).where(AiIndex.source_document_id == doc_id, AiIndex.is_current)
        )


def test_upload_is_indexed_and_visible_in_detail(api: Api) -> None:
    doc_id = _upload(api, f"politica-{uuid.uuid4().hex[:6]}.pdf", "Politica de viajes", "Viaticos")
    row = _row(api, doc_id)  # la tarea en segundo plano ya corrió (TestClient la ejecuta)
    assert row is not None and row.status == "INDEXED" and row.chunk_count >= 1
    with api.components.session_factory() as db:
        chunks = db.scalar(select(func.count(AiChunk.id)).where(AiChunk.index_id == row.id))
    assert chunks == row.chunk_count
    detail = api.client.get(
        f"/api/v1/library/documents/{doc_id}", headers=api.headers("ana@thinknex.example")
    ).json()
    assert detail["ai"]["status"] == "INDEXED"


def test_rename_reclassify_and_delete_keep_index_in_sync(api: Api) -> None:
    doc_id = _upload(api, f"acta-{uuid.uuid4().hex[:6]}.pdf", "Acta de comite")
    admin = api.admin_headers()
    url = f"/api/v1/library/documents/{doc_id}"
    api.client.patch(url, json={"name": "Acta renombrada"}, headers=admin)
    assert _row(api, doc_id).title == "Acta renombrada"  # type: ignore[union-attr]

    api.client.patch(url, json={"classification": "RESTRICTED"}, headers=admin)
    row = _row(api, doc_id)
    assert row is not None and row.status == "SKIPPED" and row.chunk_count == 0

    api.client.delete(url, headers=admin)
    with api.components.session_factory() as db:
        remaining = db.scalar(
            select(func.count(AiIndex.id)).where(AiIndex.source_document_id == doc_id)
        )
    assert remaining == 0


def test_new_version_keeps_previous_for_snapshots(api: Api) -> None:
    doc_id = _upload(api, f"informe-{uuid.uuid4().hex[:6]}.pdf", "Version uno")
    api.client.post(
        f"/api/v1/library/documents/{doc_id}/versions",
        files={"file": ("informe.pdf", make_pdf("Version dos"), "application/pdf")},
        headers=api.headers("ana@thinknex.example"),
    )
    with api.components.session_factory() as db:
        rows = db.scalars(select(AiIndex).where(AiIndex.source_document_id == doc_id)).all()
    assert len(rows) == 2
    assert sum(r.is_current for r in rows) == 1
    assert next(r for r in rows if r.is_current).version == 2


def test_backfill_indexes_existing_documents(api: Api, settings: object) -> None:
    with api.components.session_factory() as db:
        service = IndexService(db, settings, api.components.source, api.components.embedder)  # type: ignore[arg-type]
        queued = service.enqueue_all()
        assert queued >= 5
        while service.run_pending(limit=50):
            pass
    row = _row(api, "doc-public")
    assert row is not None and row.status == "INDEXED"
    assert _row(api, "doc-restricted").status == "SKIPPED"  # type: ignore[union-attr]
