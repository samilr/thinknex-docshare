import hashlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app
from app.storage import InMemoryBlobStore

API_KEY = "test-key"


@pytest.fixture
def client() -> Iterator[TestClient]:
    settings = Settings(dms_api_key=SecretStr(API_KEY))
    with TestClient(create_app(settings, InMemoryBlobStore())) as c:
        c.headers["X-API-Key"] = API_KEY
        yield c


def test_requires_api_key(client: TestClient) -> None:
    response = client.get("/documents", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_health_is_public(client: TestClient) -> None:
    del client.headers["X-API-Key"]
    assert client.get("/health").json() == {"status": "ok"}


def test_list_and_filter(client: TestClient) -> None:
    page = client.get("/documents").json()
    assert page["total"] == 6
    restricted = client.get("/documents", params={"classification": "RESTRICTED"}).json()
    assert [d["id"] for d in restricted["items"]] == ["doc-005"]
    assert "storage_key" not in page["items"][0]


def test_content_matches_published_hash(client: TestClient) -> None:
    meta = client.get("/documents/doc-002").json()
    response = client.get("/documents/doc-002/content")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    digest = hashlib.sha256(response.content).hexdigest()
    assert digest == meta["sha256"] == response.headers["x-content-sha256"]


def test_unknown_document(client: TestClient) -> None:
    assert client.get("/documents/nope").status_code == 404


def test_pdf_generation_is_deterministic() -> None:
    from app.catalog import load_seed_entries
    from app.seed import render_pdf

    entry = load_seed_entries(Settings(dms_api_key=SecretStr("x")).seed_catalog_path)[0]
    assert render_pdf(entry) == render_pdf(entry)
