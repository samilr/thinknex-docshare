# ADR-0009: Sistema documental persistente y explorador tipo SharePoint

**Estado:** aceptada

## Contexto
La primera versión trataba al sistema documental (DMS) como un catálogo de solo lectura: el portal
mostraba una tabla con un botón "Compartir". Para el uso diario se necesitaba una
expectativa más cercana a SharePoint: navegar bibliotecas y carpetas, abrir el archivo, ver quién
tiene acceso y compartir desde el propio archivo, además de subir archivos y nuevas versiones.

## Decisión
1. **El DMS simulado pasa a ser persistente y versionado.**
   - Metadata en Postgres (base `dms`, propia del servicio) y contenido en object storage con la clave
     `{doc}/v{n}.{ext}`.
   - Modelo: bibliotecas → carpetas anidadas → documentos → versiones.
   - Subidas validadas por tamaño, nombre seguro y **tipo real por magic bytes**.
   - Un nombre repetido en la misma carpeta se trata como conflicto (409) y la interfaz ofrece
     publicarlo como nueva versión.
2. **share-api orquesta la experiencia** (`/api/v1/library/*`) y agrega lo que solo él conoce:
   - accesos externos vigentes por archivo ("Personas con acceso");
   - la actividad del archivo, desde la auditoría;
   - la **vista interna con marca de agua del usuario**, auditada como `DOCUMENT_VIEWED`.
3. **Compartir no cambia** (ADR-0002): siempre se toma un snapshot inmutable de la versión vigente.
   Publicar una nueva versión no altera lo que ya recibieron los destinatarios.
4. **Autoría:** share-api informa al DMS el usuario final (`X-Acting-User`), de modo que carpetas y
   versiones quedan atribuidas a la persona, además de quedar en la auditoría.

## Alternativas descartadas
- **Integrar un SharePoint o Google Drive real:** fuera de alcance para una prueba con datos
  ficticios. La interfaz `DocumentSource` permite reemplazar el DMS simulado por un adaptador de
  Microsoft Graph o de Drive sin tocar los casos de uso.
- **Guardar la metadata en un JSON del bucket:** sin transacciones ni unicidad. Postgres ya estaba
  disponible.

## Consecuencias
- El DMS deja de ser solo lectura, así que su superficie de ataque crece. Se mitiga con la
  validación de contenido, el límite de tamaño y el acceso solo servicio a servicio (IAM y API key).
- Hay una base más en la misma instancia de Cloud SQL, sin costo adicional.
