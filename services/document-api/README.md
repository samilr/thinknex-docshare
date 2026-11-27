# document-api: sistema documental simulado (DMS)

Representa el "sistema que permite obtener documentos" del enunciado. Organiza los archivos en
**bibliotecas → carpetas → documentos → versiones**, al estilo de SharePoint. Solo se accede
servicio a servicio: share-api lo invoca con `X-API-Key` (y con ID token de Google en Cloud Run), e
informa en `X-Acting-User` el usuario final que actúa.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/libraries` | Bibliotecas con cantidad de documentos |
| GET / POST | `/folders?library_id&parent_id` | Listar o crear carpetas (nombre único por carpeta padre) |
| GET | `/folders/{id}/path` | Migas de pan |
| GET | `/documents?library_id&folder_id&q&classification` | Archivos de una ubicación, o búsqueda |
| POST | `/documents` | Subida multipart. Responde 409 `name_conflict` si el nombre ya existe en la carpeta |
| GET | `/documents/{id}` | Metadata de la versión vigente (`sha256`, `version`, `classification`) |
| GET / POST | `/documents/{id}/versions` | Historial o nueva versión (debe ser del mismo tipo) |
| GET | `/documents/{id}/content?version=` | Contenido. Headers `ETag` y `X-Content-SHA256` |
| GET | `/health` | Liveness (sin autenticación) |

- **Persistencia:** metadata en Postgres (base `dms`, migraciones con Alembic al arrancar, bajo
  advisory lock) y contenido en S3 o Cloud Storage con la clave `{doc}/v{n}.{ext}`. Los tests usan
  SQLite en memoria.
- **Subidas:** máximo 20 MB; PDF, PNG, JPEG, TXT, DOCX o XLSX. El **tipo real se valida por magic
  bytes** (un ejecutable renombrado se rechaza) y el nombre se normaliza para evitar path traversal.
- **Seed:** 6 bibliotecas con carpetas y 6 documentos ficticios (`seed/catalog.json`). Algunos
  tienen datos personales falsos para demostrar el control de sensibilidad, y `doc-001` tiene
  historial de versiones.

```bash
uv sync && uv run pytest
```
