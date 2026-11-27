"""Modelo del sistema documental: bibliotecas → carpetas → documentos → versiones.

Tipos portables (sin JSONB ni arreglos) para correr en Postgres y en SQLite (tests).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    type_annotation_map = {datetime: DateTime(timezone=True)}  # noqa: RUF012


class Library(Base):
    __tablename__ = "libraries"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(300), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (Index("ix_folders_library_parent", "library_id", "parent_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    library_id: Mapped[str] = mapped_column(ForeignKey("libraries.id"))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("folders.id"))
    name: Mapped[str] = mapped_column(String(200))
    created_by: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_location", "library_id", "folder_id"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    library_id: Mapped[str] = mapped_column(ForeignKey("libraries.id"))
    folder_id: Mapped[str | None] = mapped_column(ForeignKey("folders.id"))
    title: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(200))
    mime_type: Mapped[str] = mapped_column(String(120))
    classification: Mapped[str] = mapped_column(String(16))
    owner: Mapped[str] = mapped_column(String(320))
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)
    # Eliminación lógica: el archivo desaparece de la biblioteca, pero sus versiones y metadata se
    # conservan (trazabilidad y posible restauración).
    deleted_at: Mapped[datetime | None] = mapped_column(default=None)
    deleted_by: Mapped[str | None] = mapped_column(String(320), default=None)

    versions: Mapped[list["DocumentVersion"]] = relationship(
        order_by="DocumentVersion.version", lazy="selectin"
    )

    @property
    def current(self) -> "DocumentVersion":
        return next(v for v in self.versions if v.version == self.current_version)


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_document_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"))
    version: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(200))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
