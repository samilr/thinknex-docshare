import hashlib
import io
import zipfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.storage import InMemoryBlobStore

API_KEY = "test-key"
PDF = b"%PDF-1.4\n%fake pdf for tests\n%%EOF"


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(dms_api_key=SecretStr(API_KEY), database_url="sqlite+pysqlite:///:memory:")
    with TestClient(create_app(settings, InMemoryBlobStore())) as c:
        c.headers["X-API-Key"] = API_KEY
        c.headers["X-Acting-User"] = "ana@thinknex.example"
        yield c


def upload(client: TestClient, name: str, data: bytes, **form: str):  # type: ignore[no-untyped-def]
    fields = {"library_id": "operaciones", "classification": "INTERNAL", **form}
    return client.post("/documents", data=fields, files={"file": (name, data, "application/pdf")})


def test_requires_api_key(client: TestClient) -> None:
    assert client.get("/documents", headers={"X-API-Key": "wrong"}).status_code == 401


def test_health_is_public(client: TestClient) -> None:
    del client.headers["X-API-Key"]
    assert client.get("/health").json() == {"status": "ok", "app_env": "local"}


def test_seed_libraries_folders_and_documents(client: TestClient) -> None:
    libraries = {lib["id"]: lib for lib in client.get("/libraries").json()}
    assert set(libraries) == {"legal", "rrhh", "operaciones", "comercial", "marketing", "gerencia"}
    assert libraries["operaciones"]["document_count"] == 1
    folders = client.get("/folders", params={"library_id": "operaciones"}).json()
    informes = next(f for f in folders if f["name"] == "Informes trimestrales")
    docs = client.get(
        "/documents", params={"library_id": "operaciones", "folder_id": informes["id"]}
    ).json()
    assert [d["id"] for d in docs["items"]] == ["doc-003"]
    assert client.get("/documents").json()["total"] == 6


def test_content_matches_published_hash_and_versions(client: TestClient) -> None:
    meta = client.get("/documents/doc-001").json()
    assert meta["version"] == 2
    content = client.get("/documents/doc-001/content")
    assert hashlib.sha256(content.content).hexdigest() == meta["sha256"]
    versions = client.get("/documents/doc-001/versions").json()
    assert [v["version"] for v in versions] == [2, 1]
    v1 = client.get("/documents/doc-001/content", params={"version": 1})
    assert v1.headers["x-document-version"] == "1"
    assert hashlib.sha256(v1.content).hexdigest() == versions[1]["sha256"]


def test_upload_conflict_and_new_version(client: TestClient) -> None:
    r = upload(client, "Informe semanal.pdf", PDF, title="Informe semanal")
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["created_by"] == "ana@thinknex.example" and doc["folder_id"] is None
    conflict = upload(client, "informe SEMANAL.pdf", PDF)
    assert conflict.status_code == 409
    assert conflict.json() == {
        "detail": "Ya existe un archivo con ese nombre en esta ubicación",
        "code": "name_conflict",
        "document_id": doc["id"],
    }
    v2 = client.post(
        f"/documents/{doc['id']}/versions",
        data={"comment": "Corrige cifras"},
        files={"file": ("x.pdf", PDF + b" v2", "application/pdf")},
    )
    assert v2.status_code == 201 and v2.json()["version"] == 2
    versions = client.get(f"/documents/{doc['id']}/versions").json()
    assert versions[0]["comment"] == "Corrige cifras"


def test_new_version_must_keep_type(client: TestClient) -> None:
    doc = upload(client, "nota.pdf", PDF).json()
    r = client.post(
        f"/documents/{doc['id']}/versions", files={"file": ("nota.txt", b"hola", "text/plain")}
    )
    assert r.status_code == 422


@pytest.mark.parametrize(
    ("name", "data", "reason"),
    [
        ("malware.pdf", b"MZ\x90\x00 executable", "no corresponde"),
        ("script.exe", b"MZ", "no permitido"),
        ("vacio.pdf", b"", "vacío"),
        ("texto.txt", b"bin\x00ario", "no corresponde"),
    ],
)
def test_rejects_invalid_uploads(client: TestClient, name: str, data: bytes, reason: str) -> None:
    r = upload(client, name, data)
    assert r.status_code == 422 and reason in r.json()["detail"]


def test_rejects_oversized_upload(client: TestClient) -> None:
    big = PDF + b"0" * (20 * 1024 * 1024)
    assert upload(client, "grande.pdf", big).status_code == 422


def test_filename_is_sanitized(client: TestClient) -> None:
    r = upload(client, "../../etc/pass wd.pdf", PDF)
    assert r.status_code == 201 and r.json()["filename"] == "pass wd.pdf"


def test_docx_is_validated_by_structure(client: TestClient) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w/>")
    ok = client.post(
        "/documents",
        data={"library_id": "legal", "classification": "INTERNAL"},
        files={"file": ("acta.docx", buf.getvalue(), "application/octet-stream")},
    )
    assert ok.status_code == 201
    assert ok.json()["mime_type"].endswith("wordprocessingml.document")


def test_folders_and_breadcrumbs(client: TestClient) -> None:
    root = client.post("/folders", json={"library_id": "legal", "name": "2026"}).json()
    child = client.post(
        "/folders", json={"library_id": "legal", "parent_id": root["id"], "name": "Q4"}
    ).json()
    assert client.post("/folders", json={"library_id": "legal", "name": "2026"}).status_code == 409
    path = client.get(f"/folders/{child['id']}/path").json()
    assert [f["name"] for f in path] == ["2026", "Q4"]
    other = client.post(
        "/folders", json={"library_id": "rrhh", "parent_id": root["id"], "name": "x"}
    )
    assert other.status_code == 409, "una carpeta no puede colgar de otra biblioteca"


def test_pdf_generation_is_deterministic() -> None:
    from app.seed import load_catalog, render_pdf

    catalog = load_catalog(Settings(dms_api_key=SecretStr("x")).seed_catalog_path)
    entry = catalog.documents[0]
    assert render_pdf(entry) == render_pdf(entry)
    assert render_pdf(entry, 1) != render_pdf(entry, 2)


@pytest.mark.parametrize(
    ("app_env", "storage", "create_db"),
    [("local", "s3", True), ("hybrid", "gcs", False), ("gcp", "gcs", False)],
)
def test_profile_defaults(app_env: str, storage: str, create_db: bool) -> None:
    s = Settings(dms_api_key=SecretStr("k"), app_env=app_env)  # type: ignore[arg-type]
    assert (s.storage_backend, s.dms_create_database) == (storage, create_db)
    explicit = Settings(dms_api_key=SecretStr("k"), app_env=app_env, storage_backend="s3")  # type: ignore[arg-type]
    assert explicit.storage_backend == "s3"


def test_rename_keeps_extension_and_detects_conflicts(client: TestClient) -> None:
    first = upload(client, "Acta enero.pdf", PDF).json()
    upload(client, "Acta febrero.pdf", PDF)
    r = client.patch(f"/documents/{first['id']}", json={"name": "  Acta de enero 2026 "})
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "Acta de enero 2026"
    assert r.json()["filename"] == "Acta de enero 2026.pdf"
    assert r.json()["version"] == first["version"], "renombrar no crea una versión"

    conflict = client.patch(f"/documents/{first['id']}", json={"name": "acta FEBRERO"})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "name_conflict"
    # Cambiar solo mayúsculas del propio archivo no es conflicto.
    assert client.patch(f"/documents/{first['id']}", json={"name": "ACTA DE ENERO 2026"}).is_success
    assert client.patch(f"/documents/{first['id']}", json={"name": "../.."}).status_code == 422
    assert client.patch("/documents/doc-nope", json={"name": "x"}).status_code == 404


def test_reclassify_and_soft_delete(client: TestClient) -> None:
    doc = upload(client, "Temporal.pdf", PDF).json()
    r = client.patch(f"/documents/{doc['id']}", json={"classification": "CONFIDENTIAL"})
    assert r.status_code == 200 and r.json()["classification"] == "CONFIDENTIAL"
    assert r.json()["filename"] == "Temporal.pdf"
    before = {lib["id"]: lib["document_count"] for lib in client.get("/libraries").json()}

    assert client.delete(f"/documents/{doc['id']}").status_code == 204
    assert client.get(f"/documents/{doc['id']}").status_code == 404
    assert client.get(f"/documents/{doc['id']}/content").status_code == 404
    assert client.delete(f"/documents/{doc['id']}").status_code == 404
    listed = client.get("/documents", params={"library_id": "operaciones"}).json()["items"]
    assert doc["id"] not in {d["id"] for d in listed}
    after = {lib["id"]: lib["document_count"] for lib in client.get("/libraries").json()}
    assert after["operaciones"] == before["operaciones"] - 1
    # El nombre queda libre para volver a subir.
    assert upload(client, "Temporal.pdf", PDF).status_code == 201
