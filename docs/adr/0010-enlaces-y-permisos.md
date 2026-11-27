# ADR-0010: Enlaces de ThinkNex Docs, permisos y visor del destinatario

**Estado:** aceptada (complementa ADR-0002 y ADR-0003)

## Contexto
Hasta ahora un envío salía solo por email, WhatsApp o SMS. El destinatario validaba un código y
**descargaba** el archivo desde una página HTML mínima.

En la revisión se pidió una experiencia como la de SharePoint:
- un enlace que quien comparte copia y envía por el medio que prefiera;
- que el destinatario abra el documento **dentro de la aplicación**;
- que quien comparte decida si puede descargarlo o editarlo.

## Decisión

### 1. Canal `LINK` ("Enlace ThinkNex Docs")
- La aplicación no envía ninguna notificación.
- La respuesta de creación devuelve el enlace. Se guarda su hash (para buscarlo) y, desde la
  migración `0009`, también el token **cifrado con AES-GCM**. La clave se deriva con HKDF del secreto
  del servidor y nunca se guarda en la BD. Así quien compartió (o un ADMIN) puede volver a verlo con
  `GET /shares/{id}/link`; cada consulta se audita como `SHARE_LINK_VIEWED`.
- Si se pierde o se filtra, `POST /shares/{id}/link` **genera uno nuevo** y el anterior deja de
  funcionar. Queda auditado como `SHARE_LINK_ROTATED`.

### 2. Audiencia
- **Persona específica:** la regla de siempre, con código de un solo uso al email o teléfono del
  destinatario. Para `LINK` el código va por email si hay email y, si no, por SMS.
- **Cualquiera con el enlace:** sin verificación de identidad, así que solo se permite cuando la
  política resolvería `ALLOW` para un externo: documento público o interno, sin datos personales.
  En cualquier otro caso se bloquea con el motivo. Esta audiencia no admite `EDIT`.

### 3. Permisos, para todos los canales

| Permiso | Qué recibe el destinatario | Fuente del contenido |
|---|---|---|
| `VIEW` (solo ver) | Páginas renderizadas **en el servidor** como PNG con marca de agua. Nunca el archivo | Snapshot inmutable (ADR-0002) |
| `DOWNLOAD` (ver y descargar), el valor por defecto | Lo anterior, más el PDF con marca de agua | Snapshot inmutable |
| `EDIT` (editar) | Lo anterior, más publicar nuevas versiones | **Archivo vivo** del DMS |

- La edición se publica como versión `v+1` en el DMS, con autor `destinatario:<contacto>`, y se
  audita como `DOCUMENT_VERSION_UPLOADED` con actor `RECIPIENT`.
- `EDIT` no se permite sobre documentos `RESTRICTED`.

### 4. Visor del destinatario dentro de la SPA (`/s/{token}`)
- Consume la API pública `/api/v1/access/{token}/…` (`info`, `otp`, `verify`, `open`, `document`,
  `pages/{n}`, `text`, `download`, `versions`).
- Desde ahí la sesión es un JWT de 30 minutos ligado al envío, guardado solo en memoria.
- **Cada sesión consume un acceso**, ya sea una verificación o una apertura. Agotar el máximo no
  corta una sesión ya iniciada.

## Alternativas descartadas
- **Visor PDF en el navegador (pdf.js) con descarga oculta:** el archivo igual llega al cliente y se
  obtiene desde las herramientas de desarrollo. Renderizar en el servidor garantiza que con `VIEW`
  el archivo nunca sale.
- **Editar sobre una copia del snapshot:** produciría versiones paralelas que nadie integra. El
  usuario pidió trabajar sobre el archivo vivo.
- **Guardar el enlace en claro para poder mostrarlo de nuevo:** un volcado de la BD expondría todos
  los enlaces. Se optó por el cifrado con clave fuera de la BD: un volcado por sí solo no basta.

## Cambios posteriores
- **Editar el acceso** de un envío vigente (`PATCH /shares/{id}`): permiso, marca de agua,
  vencimiento y accesos. Aplica de inmediato, incluso a sesiones abiertas, y se audita como
  `SHARE_UPDATED` con el antes y el después.
- **Marca de agua opcional** por envío (activa por defecto, migración `0008`).

## Consecuencias
- **Honestidad sobre el alcance:** la vista protegida impide obtener el archivo, pero no evita una
  captura de pantalla (ningún visor web puede). La marca de agua identifica a quien accede y deja
  trazabilidad visible.
- Renderizar consume CPU en share-api (`pypdfium2` + Pillow). Se mitiga con una caché LRU por
  `(sha256, página)` sin marca; la marca se aplica en cada solicitud.
- **"Cualquiera con el enlace" no identifica a la persona:** la auditoría registra la apertura
  (`ACCESS_GRANTED`) con IP y user agent, no una identidad. Por eso la política lo limita a
  documentos sin datos sensibles.
- Los envíos anteriores a esta versión quedan como `DOWNLOAD` y `SPECIFIC`, con el mismo
  comportamiento que tenían.
