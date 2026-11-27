"""Puerto hacia el sistema documental existente (DMS) y su adaptador HTTP."""

import builtins
import time
from collections.abc import Generator
from datetime import datetime
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from app.core.errors import (
    ConflictError,
    NameConflictError,
    NotFoundError,
    UpstreamError,
    ValidationFailedError,
)
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
    filename: str = ""
    library_id: str = ""
    folder_id: str | None = None
    created_by: str = ""
    updated_at: datetime | None = None


class SourcePage(BaseModel):
    items: list[SourceDocument]
    total: int
    limit: int
    offset: int


class SourceLibrary(BaseModel):
    id: str
    name: str
    description: str
    document_count: int


class SourceFolder(BaseModel):
    id: str
    library_id: str
    parent_id: str | None
    name: str
    created_by: str
    created_at: datetime


class SourceVersion(BaseModel):
    version: int
    sha256: str
    size_bytes: int
    comment: str
    created_by: str
    created_at: datetime


class UploadedFile(BaseModel):
    filename: str
    content_type: str
    data: bytes


class DocumentSource(Protocol):
    def list(
        self,
        *,
        q: str | None,
        limit: int,
        offset: int,
        library_id: str | None = None,
        folder_id: str | None = None,
    ) -> SourcePage: ...
    def get_metadata(self, doc_id: str) -> SourceDocument: ...
    def get_content(self, doc_id: str, version: int | None = None) -> bytes: ...
    def versions(self, doc_id: str) -> builtins.list[SourceVersion]: ...
    def libraries(self) -> builtins.list[SourceLibrary]: ...
    def folders(self, library_id: str, parent_id: str | None) -> builtins.list[SourceFolder]: ...
    def folder_path(self, folder_id: str) -> builtins.list[SourceFolder]: ...
    def create_folder(
        self, *, library_id: str, parent_id: str | None, name: str, actor: str
    ) -> SourceFolder: ...
    def upload(
        self,
        *,
        file: UploadedFile,
        library_id: str,
        folder_id: str | None,
        classification: Classification,
        title: str | None,
        actor: str,
    ) -> SourceDocument: ...
    def upload_version(
        self, doc_id: str, *, file: UploadedFile, comment: str, actor: str
    ) -> SourceDocument: ...
    def update(
        self,
        doc_id: str,
        *,
        name: str | None,
        classification: Classification | None,
        actor: str,
    ) -> SourceDocument: ...
    def delete(self, doc_id: str, *, actor: str) -> None: ...
    def ping(self) -> bool: ...


class GoogleIdTokenAuth(httpx.Auth):
    """Agrega un ID token de Google para invocar un Cloud Run protegido por IAM.

    El token se obtiene con las credenciales del entorno (metadata server en Cloud Run) y se
    renueva antes de su vencimiento (~1 h).
    """

    def __init__(self, audience: str) -> None:
        self._audience = audience
        self._token: str | None = None
        self._expires_at = 0.0

    def _get_token(self) -> str:
        if self._token is None or time.time() > self._expires_at:
            import google.auth.transport.requests
            from google.oauth2 import id_token

            self._token = id_token.fetch_id_token(  # type: ignore[no-untyped-call]
                google.auth.transport.requests.Request(), self._audience
            )
            self._expires_at = time.time() + 50 * 60
        return self._token

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response]:
        request.headers["Authorization"] = f"Bearer {self._get_token()}"
        yield request


class HttpDocumentSource:
    def __init__(
        self, base_url: str, api_key: str, timeout: float, audience: str | None = None
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            headers={"X-API-Key": api_key},
            timeout=timeout,
            auth=GoogleIdTokenAuth(audience) if audience else None,
        )

    def _request(
        self, method: str, path: str, *, actor: str | None = None, **kwargs: Any
    ) -> httpx.Response:
        headers = {"X-Acting-User": actor} if actor else None
        try:
            response = self._client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise UpstreamError("El sistema documental no respondió") from exc
        if response.is_success:
            return response
        detail = _detail(response)
        if response.status_code == 404:
            raise NotFoundError(detail or "No encontrado en el sistema documental")
        if response.status_code == 409:
            body = response.json() if _is_json(response) else {}
            if body.get("code") == "name_conflict":
                raise NameConflictError(detail, document_id=body.get("document_id"))
            raise ConflictError(detail)
        if response.status_code == 422:
            raise ValidationFailedError(detail)
        raise UpstreamError(f"El sistema documental respondió {response.status_code}")

    def _get(self, path: str, **params: str | int | None) -> httpx.Response:
        clean = {k: v for k, v in params.items() if v is not None and v != ""}
        return self._request("GET", path, params=clean)

    def list(
        self,
        *,
        q: str | None,
        limit: int,
        offset: int,
        library_id: str | None = None,
        folder_id: str | None = None,
    ) -> SourcePage:
        response = self._get(
            "/documents",
            q=q,
            limit=limit,
            offset=offset,
            library_id=library_id,
            folder_id=folder_id,
        )
        return SourcePage.model_validate(response.json())

    def get_metadata(self, doc_id: str) -> SourceDocument:
        return SourceDocument.model_validate(self._get(f"/documents/{doc_id}").json())

    def get_content(self, doc_id: str, version: int | None = None) -> bytes:
        return self._get(f"/documents/{doc_id}/content", version=version).content

    def versions(self, doc_id: str) -> builtins.list[SourceVersion]:
        rows = self._get(f"/documents/{doc_id}/versions").json()
        return [SourceVersion.model_validate(r) for r in rows]

    def libraries(self) -> builtins.list[SourceLibrary]:
        return [SourceLibrary.model_validate(r) for r in self._get("/libraries").json()]

    def folders(self, library_id: str, parent_id: str | None) -> builtins.list[SourceFolder]:
        rows = self._get("/folders", library_id=library_id, parent_id=parent_id).json()
        return [SourceFolder.model_validate(r) for r in rows]

    def folder_path(self, folder_id: str) -> builtins.list[SourceFolder]:
        rows = self._get(f"/folders/{folder_id}/path").json()
        return [SourceFolder.model_validate(r) for r in rows]

    def create_folder(
        self, *, library_id: str, parent_id: str | None, name: str, actor: str
    ) -> SourceFolder:
        response = self._request(
            "POST",
            "/folders",
            actor=actor,
            json={"library_id": library_id, "parent_id": parent_id, "name": name},
        )
        return SourceFolder.model_validate(response.json())

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
        form = {"library_id": library_id, "classification": classification.value}
        if folder_id:
            form["folder_id"] = folder_id
        if title:
            form["title"] = title
        response = self._request(
            "POST",
            "/documents",
            actor=actor,
            data=form,
            files={"file": (file.filename, file.data, file.content_type)},
        )
        return SourceDocument.model_validate(response.json())

    def upload_version(
        self, doc_id: str, *, file: UploadedFile, comment: str, actor: str
    ) -> SourceDocument:
        response = self._request(
            "POST",
            f"/documents/{doc_id}/versions",
            actor=actor,
            data={"comment": comment},
            files={"file": (file.filename, file.data, file.content_type)},
        )
        return SourceDocument.model_validate(response.json())

    def update(
        self,
        doc_id: str,
        *,
        name: str | None,
        classification: Classification | None,
        actor: str,
    ) -> SourceDocument:
        body: dict[str, str] = {}
        if name is not None:
            body["name"] = name
        if classification is not None:
            body["classification"] = classification.value
        response = self._request("PATCH", f"/documents/{doc_id}", actor=actor, json=body)
        return SourceDocument.model_validate(response.json())

    def delete(self, doc_id: str, *, actor: str) -> None:
        self._request("DELETE", f"/documents/{doc_id}", actor=actor)

    def ping(self) -> bool:
        try:
            return self._client.get("/health").is_success
        except httpx.HTTPError:
            return False


def _is_json(response: httpx.Response) -> bool:
    content_type: str = response.headers.get("content-type", "")
    return content_type.startswith("application/json")


def _detail(response: httpx.Response) -> str:
    if not _is_json(response):
        return ""
    detail = response.json().get("detail")
    if isinstance(detail, list):
        return ". ".join(str(d.get("msg", d)) for d in detail)
    return str(detail or "")
