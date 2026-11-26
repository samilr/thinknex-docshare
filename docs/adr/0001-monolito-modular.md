# ADR-0001: Monolito modular + DMS simulado como servicio aparte

**Estado:** aceptada

## Contexto
La solución debe integrarse con un sistema documental existente y resolver la compartición
segura con auditoría. La prueba pide proporcionalidad.

## Decisión
- `share-api`: un único servicio desplegable, organizado en capas (API → servicios → adaptadores),
  con puertos explícitos (`DocumentSource`, `BlobStorage`, `ChannelAdapter`,
  `SensitivityClassifier`).
- `document-api`: un servicio aparte que **simula** el sistema existente. Se separa para que la
  integración sea real (HTTP + API key + verificación de hash) y no una llamada en memoria.

## Consecuencias
- Un solo artefacto que operar, con una sola base de datos y transacciones locales (la auditoría y
  el cambio de estado se confirman juntos).
- Los puertos permiten probar con fakes y cambiar proveedores (otro DMS, otro canal, otro storage)
  sin tocar los casos de uso.
- Si el volumen lo exigiera, se podría extraer primero el envío de notificaciones (worker) y luego
  el acceso público.
