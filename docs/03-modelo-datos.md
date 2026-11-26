# 3. Modelo de datos

PostgreSQL 17. Migraciones con Alembic: [`0001_initial.py`](../services/share-api/app/db/migrations/versions/0001_initial.py).

```mermaid
erDiagram
    USERS ||--o{ SHARES : "comparte"
    DOCUMENTS ||--o{ SHARES : "snapshot de"
    RECIPIENTS ||--o{ SHARES : "recibe"
    SHARES ||--o{ OTP_CHALLENGES : "verifica con"
    SHARES ||--o{ NOTIFICATIONS : "notifica por"
    SHARES ||..o{ AUDIT_EVENTS : "registra"
    DOCUMENTS ||..o{ AUDIT_EVENTS : "registra"

    USERS {
        uuid id PK
        string email UK
        string name
        string role "SHARER | AUDITOR"
    }
    DOCUMENTS {
        uuid id PK
        string source_id "id en el DMS"
        int source_version
        string title
        string sha256 "UK con source_id"
        string classification
        string snapshot_key "sha256/<hash>"
        timestamptz snapshot_deleted_at "retención"
    }
    RECIPIENTS {
        uuid id PK
        string name
        string email
        string phone
        bool is_external
    }
    SHARES {
        uuid id PK
        uuid document_id FK
        uuid shared_by FK
        uuid recipient_id FK
        string channel "EMAIL | WHATSAPP | SMS"
        text reason
        string token_hash UK "sha256 del token"
        string status "ACTIVE | REVOKED | EXPIRED | LOCKED | EXHAUSTED"
        timestamptz expires_at
        int max_accesses
        int access_count
        string sensitivity_decision
        jsonb sensitivity_report
    }
    OTP_CHALLENGES {
        uuid id PK
        uuid share_id FK
        string code_hmac
        timestamptz expires_at
        int attempts
        timestamptz consumed_at
    }
    NOTIFICATIONS {
        uuid id PK
        uuid share_id FK
        string channel
        string destination_masked
        string kind "LINK | OTP"
        string status "SENT | FAILED"
        string provider_message_id
    }
    AUDIT_EVENTS {
        bigint id PK
        timestamptz occurred_at
        string event_type
        string actor_type "USER | RECIPIENT | SYSTEM"
        string actor_id
        uuid share_id
        uuid document_id
        string channel
        string ip
        string user_agent
        jsonb metadata
        string prev_hash
        string hash UK
    }
```

## Diccionario y decisiones

**`shares`: el corazón del modelo.** Cada fila responde a la pregunta del negocio:
**quién** (`shared_by`), **qué** (`document_id`, que es un snapshot con hash), **a quién**
(`recipient_id`), **cuándo** (`created_at`), **por qué medio** (`channel`) y **para qué** (`reason`).
Las restricciones `CHECK` garantizan valores válidos de `channel` y `status`, y que
`0 ≤ access_count ≤ max_accesses`.

**`documents`: snapshot, no espejo del DMS.** Una fila por `(source_id, sha256)`: si el documento
cambia en el DMS, el próximo share crea un snapshot nuevo y los anteriores siguen apuntando a lo que
realmente se compartió. `snapshot_key` es direccionado por contenido, así que compartir 10 veces el
mismo archivo lo guarda una sola vez.

**`recipients`**: se reutilizan por email o teléfono. `is_external` sigue el supuesto S1 (dominio
corporativo). `CHECK` exige al menos un dato de contacto.

**`otp_challenges`**: solo se guarda el HMAC del código. Un único código vigente por share (los
anteriores se marcan consumidos), con un máximo de 5 intentos por código y 5 códigos por share.

**`notifications`**: registro técnico de cada envío, con el destino enmascarado y el id del proveedor
para conciliar con WhatsApp o SMS. Nunca guarda el cuerpo del mensaje, porque contiene el enlace o el
OTP.

**`audit_events`: append-only y encadenada.**
- Sin claves foráneas a propósito: la auditoría debe sobrevivir a cualquier limpieza de otras tablas.
- `hash = sha256(prev_hash ‖ JSON canónico del evento)`. `GET /api/v1/audit/verify` la recalcula.
- Los triggers `audit_events_no_update_delete` y `audit_events_no_truncate` rechazan cualquier
  modificación, incluso de la propia aplicación.
- `metadata` nunca contiene datos personales en claro: contactos enmascarados, conteos de hallazgos
  por tipo y el `sha256` del documento (prueba de qué se compartió aun después de purgar el contenido).

### Catálogo de eventos de auditoría

| Evento | Actor | Cuándo |
|---|---|---|
| `SENSITIVITY_CHECKED` | USER | Al evaluar un documento para compartir (incluye la decisión) |
| `SHARE_BLOCKED` | USER | Política impidió compartir |
| `SHARE_CREATED` | USER | Share creado (motivo, vencimiento, límites, hash) |
| `NOTIFICATION_SENT` / `NOTIFICATION_FAILED` | SYSTEM | Envío del enlace por el canal |
| `LINK_OPENED` | RECIPIENT | Apertura de la página |
| `OTP_SENT` / `OTP_VERIFIED` / `OTP_FAILED` | RECIPIENT | Verificación de identidad |
| `DOCUMENT_ACCESSED` | RECIPIENT | Descarga (número de acceso y marca de agua) |
| `ACCESS_DENIED` | RECIPIENT | Cualquier denegación, con la causa real |
| `SHARE_REVOKED` | USER | Revocación |
| `SHARE_EXPIRED` / `SHARE_LOCKED` | SYSTEM | Vencimiento o bloqueo por intentos |
| `SNAPSHOT_PURGED` | SYSTEM | Retención: contenido eliminado, hash conservado |

### Índices

`shares(token_hash)` único (búsqueda por enlace), `shares(shared_by)`,
`audit_events(document_id, occurred_at)`, `audit_events(actor_id)`, `audit_events(share_id)` y
`otp_challenges(share_id, created_at)`.
