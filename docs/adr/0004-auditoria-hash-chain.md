# ADR-0004: Auditoría append-only con cadena de hashes

**Estado:** aceptada

## Contexto
El requisito central es registrar quién, cuándo y por qué medio. Un registro que se puede editar
en silencio no sirve como evidencia.

## Decisión
- Tabla `audit_events` **en la misma transacción** que el cambio de negocio: si una operación se
  confirma, su evento también. Las denegaciones se confirman explícitamente antes de responder
  el error.
- Triggers de PostgreSQL que rechazan `UPDATE`, `DELETE` y `TRUNCATE`.
- `hash_n = sha256(hash_{n-1} ‖ JSON canónico(evento_n))`, con inserciones serializadas mediante
  `pg_advisory_xact_lock`. `GET /api/v1/audit/verify` recalcula la cadena e informa el primer
  eslabón roto.
- Sin datos personales en claro dentro de `metadata`.

## Alternativas descartadas
- Logs de aplicación: no son consultables por negocio y son fáciles de perder.
- Ledger externo o blockchain: desproporcionado. El anclaje diario del último hash en un storage
  WORM queda en el roadmap y da la misma garantía frente a un DBA.

## Consecuencias
- Detecta manipulación incluso por alguien que deshabilite el trigger (cubierto por un test).
- La escritura de eventos es secuencial, lo que basta para el volumen esperado. Si no bastara, se
  usarían cadenas particionadas.
