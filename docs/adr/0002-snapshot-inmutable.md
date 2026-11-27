# ADR-0002: Snapshot inmutable direccionado por contenido

**Estado:** aceptada

## Contexto
Hay que decidir si guardar una referencia al documento del DMS y servirlo en vivo, o copiarlo al
compartir.

## Decisión
Al compartir se copia el contenido a un object storage S3-compatible con la clave
`sha256/<hash>`, después de verificar que el hash coincide con el publicado por el DMS. El share
apunta a ese snapshot.

- **Deduplicación:** el mismo contenido compartido N veces se guarda una vez.
- **Retención:** `make gc` purga el snapshot cuando ningún share que lo usa está activo ni venció
  hace menos de `SNAPSHOT_GRACE_HOURS`. El hash permanece en la auditoría.
- **Storage local:** SeaweedFS (S3-compatible). Se descartó MinIO porque sus imágenes públicas ya
  no están disponibles. En la nube: S3, Azure Blob o GCS con cifrado KMS.

## Alternativas descartadas
- **Proxy en vivo al DMS:** si el documento cambia, el destinatario recibe algo distinto de lo que se
  compartió y la auditoría pierde valor probatorio. Además, el acceso depende de que el DMS esté
  disponible. Si el DMS ofreciera versiones inmutables con ID, guardar `source_id + version + hash`
  sería una opción válida sin duplicar datos.

## Consecuencias
Existe una segunda copia de información sensible, mitigada con una retención corta y el cifrado
en reposo del bucket.
