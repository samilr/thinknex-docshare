# document-api — sistema documental simulado (DMS)

Representa el "sistema que permite obtener documentos" que menciona el enunciado. Es un **simulador
deliberadamente liviano**: no es parte de la solución, solo provee documentos ficticios a `share-api`
como lo haría el sistema real a través de su API.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/documents?q=&classification=&limit=&offset=` | Catálogo paginado |
| GET | `/documents/{id}` | Metadata (incluye `sha256`, `version`, `classification`) |
| GET | `/documents/{id}/content` | Contenido binario. Headers `ETag` y `X-Content-SHA256` |
| GET | `/health` | Liveness (sin autenticación) |

- Autenticación servicio a servicio mediante el header `X-API-Key` (valor en la variable `DMS_API_KEY`).
- Los archivos viven en el bucket `dms-documents` (S3-compatible; SeaweedFS en local). Al arrancar con `DMS_AUTO_SEED=true`
  se generan 6 PDFs ficticios definidos en [`seed/catalog.json`](seed/catalog.json); algunos contienen
  datos personales **falsos** a propósito (RUT, cuentas, tarjetas de prueba) para demostrar el control
  de sensibilidad de `share-api`.

```bash
uv sync && uv run pytest        # tests con almacenamiento en memoria
```
