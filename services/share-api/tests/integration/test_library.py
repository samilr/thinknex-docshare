import io
import uuid

import pytest
from pypdf import PdfReader

from tests.helpers import make_pdf
from tests.integration.conftest import Api

pytestmark = pytest.mark.integration


def ana(api: Api) -> dict[str, str]:
    return api.headers("ana@thinknex.example")


def upload(api: Api, name: str, data: bytes, **form: str):  # type: ignore[no-untyped-def]
    fields = {"library_id": "comercial", "classification": "INTERNAL", **form}
    return api.client.post(
        "/api/v1/library/documents",
        data=fields,
        files={"file": (name, data, "application/pdf")},
        headers=ana(api),
    )


def test_browse_libraries_and_folders(api: Api) -> None:
    headers = ana(api)
    libraries = api.client.get("/api/v1/library/libraries", headers=headers).json()
    assert {lib["id"] for lib in libraries} >= {"operaciones", "legal", "comercial"}

    name = f"Contratos {uuid.uuid4().hex[:4]}"
    folder = api.client.post(
        "/api/v1/library/folders", json={"library_id": "legal", "name": name}, headers=headers
    )
    assert folder.status_code == 201
    dup = api.client.post(
        "/api/v1/library/folders", json={"library_id": "legal", "name": name}, headers=headers
    )
    assert dup.status_code == 409
    child = api.client.post(
        "/api/v1/library/folders",
        json={"library_id": "legal", "parent_id": folder.json()["id"], "name": "2026"},
        headers=headers,
    ).json()

    items = api.client.get(
        "/api/v1/library/items",
        params={"library_id": "legal", "folder_id": child["id"]},
        headers=headers,
    ).json()
    assert [b["name"] for b in items["breadcrumbs"]] == [name, "2026"]
    assert items["library"]["id"] == "legal"
    assert api.audit(event_type="FOLDER_CREATED")


def test_upload_detects_personal_data_and_is_audited(api: Api) -> None:
    name = f"cliente-{uuid.uuid4().hex[:6]}.pdf"
    r = upload(api, name, make_pdf("Cliente con RUT 17.234.567-0"))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["new_version"] is False
    assert [f["type"] for f in body["findings"]] == ["RUT"]
    assert "17.234.567-0" not in r.text, "los valores detectados nunca se devuelven en claro"
    uploaded = api.audit(event_type="DOCUMENT_UPLOADED")[0]
    assert uploaded["metadata"]["source_document_id"] == body["document"]["id"]  # type: ignore[index]
    assert uploaded["metadata"]["findings"] == {"RUT": 1}  # type: ignore[index]


def test_name_conflict_then_new_version(api: Api) -> None:
    name = f"informe-{uuid.uuid4().hex[:6]}.pdf"
    first = upload(api, name, make_pdf("v1")).json()["document"]
    conflict = upload(api, name, make_pdf("v1 bis"))
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "name_conflict"
    assert conflict.json()["document_id"] == first["id"]

    r = api.client.post(
        f"/api/v1/library/documents/{first['id']}/versions",
        data={"comment": "Cifras corregidas"},
        files={"file": (name, make_pdf("v2"), "application/pdf")},
        headers=ana(api),
    )
    assert r.status_code == 201 and r.json()["document"]["version"] == 2
    detail = api.client.get(f"/api/v1/library/documents/{first['id']}", headers=ana(api)).json()
    assert [v["version"] for v in detail["versions"]] == [2, 1]
    assert detail["versions"][0]["comment"] == "Cifras corregidas"


def test_internal_view_is_watermarked_and_audited(api: Api) -> None:
    doc = upload(api, f"vista-{uuid.uuid4().hex[:6]}.pdf", make_pdf("Contenido interno")).json()
    doc_id = doc["document"]["id"]
    r = api.client.get(f"/api/v1/library/documents/{doc_id}/content", headers=ana(api))
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("inline")
    assert r.headers["cache-control"] == "no-store"
    text = PdfReader(io.BytesIO(r.content)).pages[0].extract_text()
    assert "Contenido interno" in text and "Vista interna · ana@thinknex.example" in text

    download = api.client.get(
        f"/api/v1/library/documents/{doc_id}/content",
        params={"disposition": "attachment", "version": 1},
        headers=ana(api),
    )
    assert download.headers["content-disposition"].startswith("attachment")
    viewed = [
        e
        for e in api.audit(event_type="DOCUMENT_VIEWED")
        if e["metadata"]["source_document_id"] == doc_id  # type: ignore[index]
    ]
    assert {e["metadata"]["mode"] for e in viewed} == {"preview", "download"}  # type: ignore[index]


def test_share_from_library_shows_access_and_activity(api: Api) -> None:
    doc = upload(api, f"compartir-{uuid.uuid4().hex[:6]}.pdf", make_pdf("Propuesta")).json()
    doc_id = doc["document"]["id"]
    api.share(document_id=doc_id)

    items = api.client.get(
        "/api/v1/library/items", params={"library_id": "comercial"}, headers=ana(api)
    ).json()
    listed = next(d for d in items["documents"] if d["id"] == doc_id)
    assert listed["active_shares"] == 1

    access = api.client.get(f"/api/v1/library/documents/{doc_id}/access", headers=ana(api)).json()
    assert len(access) == 1 and access[0]["recipient"]["name"] == "Pedro Externo"

    activity = api.client.get(
        f"/api/v1/library/documents/{doc_id}/activity", headers=ana(api)
    ).json()
    types = {e["event_type"] for e in activity}
    assert {"DOCUMENT_UPLOADED", "SENSITIVITY_CHECKED", "SHARE_CREATED"} <= types


def test_library_requires_sharer_role(api: Api) -> None:
    carla = api.headers("carla@thinknex.example")
    assert api.client.get("/api/v1/library/libraries", headers=carla).status_code == 403
    r = api.client.post(
        "/api/v1/library/documents",
        data={"library_id": "comercial", "classification": "INTERNAL"},
        files={"file": ("x.pdf", make_pdf("x"), "application/pdf")},
        headers=carla,
    )
    assert r.status_code == 403


def test_invalid_content_is_rejected(api: Api) -> None:
    r = upload(api, "malware.pdf", b"MZ\x90\x00 not a pdf")
    assert r.status_code == 422
