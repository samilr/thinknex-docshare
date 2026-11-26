# 2. Diseño

## 2.1 Arquitectura

```mermaid
flowchart LR
    subgraph Interno["Organización"]
        U["Usuario interno<br/>(SHARER / AUDITOR)"]
        subgraph SA["share-api (FastAPI)"]
            API["API v1<br/>shares · audit · documents"]
            PUB["Acceso público<br/>/s/{token}"]
            SVC["Servicios<br/>share · access · audit · retention"]
            SENS["Sensibilidad<br/>reglas + LLM opcional"]
        end
        DMS["document-api<br/>(DMS existente, simulado)"]
        PG[("PostgreSQL<br/>shares · auditoría")]
        S3[("Object storage S3<br/>snapshots por sha256")]
    end
    subgraph Canales
        MAIL["Email (SMTP)"]
        WA["WhatsApp (simulado)"]
        SMS["SMS (simulado)"]
    end
    R["Destinatario<br/>(sin cuenta)"]
    LLM["Claude API<br/>(opcional, texto redactado)"]

    U -- "JWT (OIDC en prod)" --> API
    API --> SVC
    PUB --> SVC
    SVC -- "X-API-Key" --> DMS
    SVC --> PG
    SVC --> S3
    SVC --> SENS
    SENS -. "flag" .-> LLM
    SVC -- "solo enlace / OTP" --> MAIL & WA & SMS
    MAIL & WA & SMS --> R
    R -- "enlace + OTP" --> PUB
```

**Estilo:** monolito modular (un servicio, capas separadas) más el DMS como sistema externo. Es
proporcional al problema: un dominio acotado y un volumen moderado. Los módulos tienen límites
claros (puertos y adaptadores), así que se podrían extraer si el volumen lo justificara (ver
ADR-0001).

## 2.2 Componentes y responsabilidades

| Componente | Responsabilidad | Ubicación |
|---|---|---|
| `document-api` | Simula el sistema existente: catálogo, metadata con `sha256` y clasificación, y contenido | `services/document-api` |
| API v1 | Endpoints internos autenticados con roles | `app/api/v1/` |
| Acceso público | Página y endpoints del destinatario (`/s/{token}`) | `app/api/public/` |
| `ShareService` | Caso de uso de compartir: verificar integridad, aplicar la política, tomar el snapshot, persistir, notificar y auditar | `app/services/share_service.py` |
| `AccessService` | Abrir enlace, OTP, verificación, descarga con consumo atómico y marca de agua | `app/services/access_service.py` |
| `audit_service` | Auditoría append-only con cadena de hashes, consultas y verificación | `app/services/audit_service.py` |
| `retention_service` | Vencer shares y purgar snapshots sin uso | `app/services/retention_service.py` |
| Sensibilidad | Detectores (RUT, email, teléfono, tarjeta, cuenta), política y LLM opcional | `app/sensitivity/` |
| Adaptadores | DMS (HTTP), storage (S3), canales (SMTP y mocks), marca de agua (PDF) | `app/adapters/` |
| Composition root | Arma las dependencias concretas. Los tests inyectan fakes | `app/container.py` |

## 2.3 Flujo principal: compartir

```mermaid
sequenceDiagram
    autonumber
    actor A as Ana (SHARER)
    participant S as share-api
    participant D as document-api (DMS)
    participant O as Object storage
    participant DB as PostgreSQL
    participant C as Canal (email/WhatsApp/SMS)
    actor P as Destinatario

    A->>S: POST /api/v1/shares {doc, destinatario, canal, motivo}
    S->>D: GET metadata + contenido
    S->>S: verifica sha256 (integridad)
    S->>S: chequeo de sensibilidad → ALLOW / WARN / BLOCK
    S->>DB: audit SENSITIVITY_CHECKED
    alt BLOCK
        S->>DB: audit SHARE_BLOCKED (commit)
        S-->>A: 403 problem+json
    else WARN sin confirmar
        S-->>A: 409 + hallazgos (enmascarados)
    else ALLOW o WARN confirmado
        S->>O: put sha256/<hash> (si no existe)
        S->>DB: share (token_hash), audit SHARE_CREATED
        S->>C: enlace /s/{token}
        S->>DB: notification + audit NOTIFICATION_SENT
        S-->>A: 201 (sin el enlace)
        C-->>P: "Ana compartió un documento contigo: <enlace>"
    end
```

## 2.4 Flujo del destinatario: acceso

```mermaid
sequenceDiagram
    autonumber
    actor P as Destinatario
    participant S as share-api
    participant DB as PostgreSQL
    participant O as Object storage
    participant C as Canal

    P->>S: GET /s/{token}
    S->>DB: busca por sha256(token), valida estado y vencimiento
    S-->>P: página (sin título del documento) + audit LINK_OPENED
    P->>S: POST /s/{token}/otp
    S->>C: código de 6 dígitos (HMAC en BD, TTL 10 min)
    P->>S: POST /s/{token}/verify {code}
    alt código incorrecto (5 veces)
        S->>DB: share → LOCKED, audit OTP_FAILED / SHARE_LOCKED
    else correcto
        S-->>P: token de descarga (JWT 5 min, ligado al share)
    end
    P->>S: GET /s/{token}/download (Bearer)
    S->>O: snapshot + verificación sha256
    S->>DB: UPDATE access_count+1 WHERE access_count < max (atómico)
    S-->>P: PDF con marca de agua + audit DOCUMENT_ACCESSED
```

Las denegaciones (token desconocido, vencido, revocado, agotado o bloqueado) responden igual hacia
afuera (`404 link_unavailable`), y la causa real queda en la auditoría (`ACCESS_DENIED.reason`).

## 2.5 Decisiones de diseño y justificación

| Decisión | Alternativa descartada | Por qué |
|---|---|---|
| **Enlace + OTP**, el documento no viaja por el canal (ADR-0003) | Adjuntar el archivo | Sin enlace no hay revocación, expiración ni registro de accesos |
| **Snapshot inmutable por sha256** (ADR-0002) | Proxy en vivo al DMS | Lo compartido es exactamente lo descargado. Deduplica y no depende de que el DMS esté disponible |
| **Auditoría con cadena de hashes y trigger** (ADR-0004) | Tabla de logs simple | Evidencia de manipulación verificable a bajo costo |
| **Solo se guarda el hash del token** | Guardar el token | Un volcado de la BD no permite usar enlaces |
| **OTP como HMAC ligado al share** | OTP en claro | Un volcado no revela códigos y un código no sirve para otro share |
| **Respuesta uniforme a denegaciones** | Mensajes específicos | Evita enumerar enlaces. El detalle queda en la auditoría |
| **GET de la página no consume accesos** | Consumir al abrir | Los previsualizadores de email y WhatsApp abren los enlaces automáticamente |
| **IA solo puede advertir, nunca bloquear** (ADR-0005) | Decisión automática por LLM | Un falso positivo no debe impedir trabajar. La persona decide con la información a la vista |
| **SQLAlchemy síncrono** | async | boto3 y smtplib son síncronos. El threadpool de FastAPI basta para el volumen esperado |
| **Problem Details (RFC 7807)** | Errores ad hoc | Contrato de errores estándar y extensible (`report`, `remaining_attempts`) |

## 2.6 Seguridad transversal

- **Secretos** solo por variables de entorno (`.env` local, gestor de secretos en producción). La
  configuración exige al menos 32 caracteres para `JWT_SECRET` y `OTP_SECRET`.
- **Logs** en JSON con `request_id`. Las rutas `/s/{token}` se registran como `/s/***` y el access
  log de uvicorn está desactivado.
- **Headers** en `/s/*`: `Cache-Control: no-store`, `Referrer-Policy: no-referrer`,
  `X-Frame-Options: DENY` y CSP estricta con nonce.
- **Contenedores** sin root, con imágenes multi-stage y healthchecks.
- **Integridad** del contenido verificada dos veces: al leer del DMS y al servir el snapshot.
