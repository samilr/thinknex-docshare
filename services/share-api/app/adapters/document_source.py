"""Puerto hacia el sistema documental existente (DMS) y su adaptador HTTP."""

from typing import Protocol

import httpx
from pydantic import BaseModel

from app.core.errors import NotFoundError, UpstreamError
from app.domain.enums import Classification


class SourceDocument(BaseModel):
    id: str
    title: str
    mime_type: str
    size_bytes: int
    sha256: str
    version: int
    classification: Classification
    owner: str


class SourcePage(BaseModel):
    items: list[SourceDocument]
    total: int
    limit: int
    offset: int


class DocumentSource(Protocol):
    def list(self, *, q: str | None, limit: int, offset: int) -> SourcePage: ...
    def get_metadata(self, doc_id: str) -> SourceDocument: ...
    def get_content(self, doc_id: str) -> bytes: ...
    def ping(self) -> bool: ...


class HttpDocumentSource:
    def __init__(self, base_url: str, api_key: str, timeout: float) -> None:
        self._client = httpx.Client(
            base_url=base_url, headers={"X-API-Key": api_key}, timeout=timeout
        )

    def _get(self, path: str, **params: str | int | None) -> httpx.Response:
        try:
            response = self._client.get(path, params={k: v for k, v in params.items() if v})
        except httpx.HTTPError as exc:
            raise UpstreamError("El sistema documental no respondió") from exc
        if response.status_code == 404:
            raise NotFoundError("Documento no encontrado en el sistema documental")
        if response.is_error:
            raise UpstreamError(f"El sistema documental respondió {response.status_code}")
        return response

    def list(self, *, q: str | None, limit: int, offset: int) -> SourcePage:
        return SourcePage.model_validate(
            self._get("/documents", q=q, limit=limit, offset=offset).json()
        )

    def get_metadata(self, doc_id: str) -> SourceDocument:
        return SourceDocument.model_validate(self._get(f"/documents/{doc_id}").json())

    def get_content(self, doc_id: str) -> bytes:
        return self._get(f"/documents/{doc_id}/content").content

    def ping(self) -> bool:
        try:
            return self._client.get("/health").is_success
        except httpx.HTTPError:
            return False
