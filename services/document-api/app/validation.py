"""Validación de archivos subidos: tamaño, nombre seguro y tipo real por magic bytes.

La extensión declarada debe coincidir con el contenido real: un ejecutable renombrado a .pdf se
rechaza aunque el navegador declare application/pdf.
"""

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import PurePath


class InvalidUpload(ValueError):
    pass


@dataclass(frozen=True)
class FileType:
    extension: str
    mime_type: str


ALLOWED: dict[str, FileType] = {
    "pdf": FileType("pdf", "application/pdf"),
    "png": FileType("png", "image/png"),
    "jpg": FileType("jpg", "image/jpeg"),
    "jpeg": FileType("jpeg", "image/jpeg"),
    "txt": FileType("txt", "text/plain"),
    "docx": FileType(
        "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    "xlsx": FileType("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
}


def safe_filename(raw: str) -> str:
    """Solo el nombre base, sin rutas ni caracteres de control, con longitud acotada."""
    name = PurePath(raw.replace("\\", "/")).name
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r"[\x00-\x1f\x7f<>:\"/\\|?*]", "", name).strip(" .")
    if not name or "." not in name:
        raise InvalidUpload("Nombre de archivo inválido")
    stem, ext = name.rsplit(".", 1)
    return f"{stem[:150]}.{ext.lower()}"


def _zip_contains(data: bytes, prefix: str) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return any(n.startswith(prefix) for n in archive.namelist())
    except zipfile.BadZipFile:
        return False


def _matches(ext: str, data: bytes) -> bool:
    if ext == "pdf":
        return data.startswith(b"%PDF-")
    if ext == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in ("jpg", "jpeg"):
        return data.startswith(b"\xff\xd8\xff")
    if ext == "docx":
        return data.startswith(b"PK\x03\x04") and _zip_contains(data, "word/")
    if ext == "xlsx":
        return data.startswith(b"PK\x03\x04") and _zip_contains(data, "xl/")
    if ext == "txt":
        if b"\x00" in data:
            return False
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return True
    return False


def validate_upload(filename: str, data: bytes, max_bytes: int) -> tuple[str, FileType]:
    if not data:
        raise InvalidUpload("El archivo está vacío")
    if len(data) > max_bytes:
        raise InvalidUpload(f"El archivo supera el máximo de {max_bytes // (1024 * 1024)} MB")
    name = safe_filename(filename)
    ext = name.rsplit(".", 1)[1]
    file_type = ALLOWED.get(ext)
    if file_type is None:
        allowed = ", ".join(sorted({t.extension for t in ALLOWED.values()}))
        raise InvalidUpload(f"Tipo de archivo no permitido. Permitidos: {allowed}")
    if not _matches(ext, data):
        raise InvalidUpload("El contenido del archivo no corresponde a su extensión")
    return name, file_type
