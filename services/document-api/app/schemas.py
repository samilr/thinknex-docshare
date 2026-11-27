from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Classification(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class LibraryOut(BaseModel):
    id: str
    name: str
    description: str
    document_count: int


class FolderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    library_id: str
    parent_id: str | None
    name: str
    created_by: str
    created_at: datetime


class FolderCreate(BaseModel):
    library_id: str
    parent_id: str | None = None
    name: str = Field(min_length=1, max_length=200)


class DocumentUpdate(BaseModel):
    """Cambios de metadata. Nombre sin extensión: la define el tipo real del archivo."""

    name: str | None = Field(default=None, min_length=1, max_length=150)
    classification: Classification | None = None


class DocumentMeta(BaseModel):
    id: str
    title: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    version: int
    classification: Classification
    owner: str
    library_id: str
    folder_id: str | None
    created_by: str
    updated_at: datetime


class DocumentPage(BaseModel):
    items: list[DocumentMeta]
    total: int
    limit: int
    offset: int


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    sha256: str
    size_bytes: int
    comment: str
    created_by: str
    created_at: datetime


# --- seed --------------------------------------------------------------------------------
class SeedLibrary(BaseModel):
    id: str
    name: str
    description: str
    folders: list[str]


class SeedDocument(BaseModel):
    id: str
    title: str
    classification: Classification
    owner: str
    version: int
    paragraphs: list[str]
    library: str
    folder: str | None
    filename: str


class SeedCatalog(BaseModel):
    libraries: list[SeedLibrary]
    documents: list[SeedDocument]
