"""Catálogo en memoria del DMS simulado.

La metadata se reconstruye al arrancar leyendo cada objeto del almacenamiento, de modo que el
``sha256`` publicado corresponde siempre al contenido real servido.
"""

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from app.storage import BlobStore


class Classification(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class SeedEntry(BaseModel):
    id: str
    title: str
    classification: Classification
    owner: str
    version: int
    paragraphs: list[str]

    @property
    def storage_key(self) -> str:
        return f"{self.id}/v{self.version}.pdf"


class DocumentMeta(BaseModel):
    id: str
    title: str
    mime_type: str = "application/pdf"
    size_bytes: int
    sha256: str
    version: int
    classification: Classification
    owner: str
    updated_at: datetime
    storage_key: str = Field(exclude=True)


class DocumentPage(BaseModel):
    items: list[DocumentMeta]
    total: int
    limit: int
    offset: int


def load_seed_entries(path: Path) -> list[SeedEntry]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [SeedEntry.model_validate(item) for item in raw]


class Catalog:
    def __init__(self, store: BlobStore) -> None:
        self._store = store
        self._docs: dict[str, DocumentMeta] = {}

    def load(self, entries: list[SeedEntry]) -> None:
        loaded_at = datetime.now(UTC)
        for entry in entries:
            data = self._store.get(entry.storage_key)
            self._docs[entry.id] = DocumentMeta(
                id=entry.id,
                title=entry.title,
                size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
                version=entry.version,
                classification=entry.classification,
                owner=entry.owner,
                updated_at=loaded_at,
                storage_key=entry.storage_key,
            )

    def list(
        self,
        *,
        q: str | None,
        classification: Classification | None,
        limit: int,
        offset: int,
    ) -> DocumentPage:
        docs = sorted(self._docs.values(), key=lambda d: d.id)
        if q:
            needle = q.casefold()
            docs = [d for d in docs if needle in d.title.casefold()]
        if classification:
            docs = [d for d in docs if d.classification == classification]
        return DocumentPage(
            items=docs[offset : offset + limit], total=len(docs), limit=limit, offset=offset
        )

    def get(self, doc_id: str) -> DocumentMeta | None:
        return self._docs.get(doc_id)

    def content(self, doc: DocumentMeta) -> bytes:
        return self._store.get(doc.storage_key)
