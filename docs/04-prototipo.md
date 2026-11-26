# 4. Prototipo

## 4.1 Flujo elegido y por qué

Se implementó el **flujo completo de punta a punta**: compartir → notificar → verificar al
destinatario → descargar → auditar, incluidos los caminos negativos. Es la cadena que entrega el
valor de negocio: implementar solo una parte (por ejemplo, el registro) no demostraría que el
documento se comparte **de forma segura**, que es lo difícil del problema.

| Capacidad | Estado | Dónde verlo |
|---|---|---|
| Compartir por email (SMTP real a Mailpit) | ✅ | `make demo` paso 2, http://localhost:8025 |
| Compartir por WhatsApp y SMS (simulados) | ✅ | `make demo` pasos 4 y 7, bandeja simulada `GET /api/v1/admin/inbox` |
| OTP, descarga y marca de agua | ✅ | `make demo` paso 3, `out/doc-003-compartido.pdf` |
| Expiración, límite de accesos y revocación | ✅ | Pasos 6 y 7, tests de integración |
| Política de sensibilidad (reglas) | ✅ | Pasos 4 y 5 |
| Sensibilidad asistida por LLM | ✅ opcional | `SENSITIVITY_LLM_ENABLED=true` + `ANTHROPIC_API_KEY` |
| Auditoría: quién, cuándo y por qué medio | ✅ | Paso 8, `GET /api/v1/audit?document_id=doc-003` |
| Integridad y append-only | ✅ | Paso 9, `GET /api/v1/audit/verify` |
| Retención de snapshots | ✅ | `make gc`, test `test_retention_purges_snapshot_but_keeps_hash` |

## 4.2 Ejecución

Requisitos: Docker (con Compose v2), `make`, `curl` y `jq`. Para correr los tests: [`uv`](https://docs.astral.sh/uv/).

```bash
cp .env.example .env     # valores locales ficticios; make up lo hace si falta
make up                  # postgres, s3 (SeaweedFS), mailpit, document-api, share-api
make demo                # recorre los 9 pasos del flujo con curl
make test                # 51 tests: unitarios + integración contra Postgres real
make lint                # ruff + mypy --strict
make down                # o `make reset` para borrar también los datos
```

| URL | Qué es |
|---|---|
| http://localhost:8000/docs | Swagger de share-api (botón **Authorize**: `ana@demo-corp.example` / `Demo-pass-2026`) |
| http://localhost:8001/docs | Swagger del DMS simulado (header `X-API-Key`, ver `.env`) |
| http://localhost:8025 | Bandeja de Mailpit: emails con enlace y OTP |
| http://localhost:8000/s/{token} | Página del destinatario (el enlace llega por el canal) |

### Usuarios ficticios

| Usuario | Rol | Puede |
|---|---|---|
| `ana@demo-corp.example` | SHARER | Compartir, listar y revocar sus shares |
| `bruno@demo-corp.example` | SHARER | Igual que Ana (para probar que no puede revocar lo de Ana) |
| `carla@demo-corp.example` | AUDITOR | Consultar y verificar la auditoría |

Contraseña: el valor de `DEMO_USERS_PASSWORD` en `.env` (por defecto `Demo-pass-2026`). El ADMIN
inicial es `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`.

### Documentos del DMS simulado

| ID | Clasificación | Qué demuestra |
|---|---|---|
| doc-001 | CONFIDENTIAL | Contrato con RUT de empresa y de persona. WARN hacia externos |
| doc-002 | CONFIDENTIAL | Liquidación con RUT, cuenta bancaria y email. WARN hacia externos |
| doc-003 | INTERNAL | Sin datos personales. ALLOW: el flujo feliz |
| doc-004 | PUBLIC | Catálogo. ALLOW |
| doc-005 | RESTRICTED | BLOCK hacia externos y WARN hacia internos |
| doc-006 | INTERNAL | RUT, teléfono y tarjeta de prueba. WARN hacia externos |

## 4.3 Probar el flujo a mano (Swagger)

1. En http://localhost:8000/docs, **Authorize** con `ana@demo-corp.example`.
2. `POST /api/v1/shares` con:
   ```json
   {"document_id": "doc-003", "recipient": {"name": "Pedro", "email": "pedro@auditora.example"},
    "channel": "EMAIL", "reason": "Auditoría Q3"}
   ```
3. Abrir el email en http://localhost:8025, hacer clic en el enlace, pedir el código, leerlo en
   Mailpit, verificar y descargar.
4. **Authorize** con `carla@demo-corp.example` y llamar `GET /api/v1/audit?document_id=doc-003`.

## 4.4 Activar la IA

```bash
# en .env
SENSITIVITY_LLM_ENABLED=true
ANTHROPIC_API_KEY=<tu clave>
docker compose up -d share-api
```

`POST /api/v1/shares/precheck` devolverá `engine: "rules+llm"` y el bloque `llm` con la
sensibilidad, las categorías y una justificación. Si la API no responde, el sistema degrada a
`engine: "rules (llm no disponible)"` sin fallar.

## 4.5 Tests

| Suite | Qué cubre |
|---|---|
| `document-api/tests` (6) | API key, filtros, hash publicado = contenido, determinismo del seed |
| `share-api/tests/unit` (30) | Detectores (RUT con dígito verificador, Luhn, solapamientos), matriz de política, IA solo advierte, redacción antes del LLM, JWT con tipos, OTP ligado al share, marca de agua, hash canónico, redacción de logs |
| `share-api/tests/integration` (15) | Flujo E2E, 409 / 403 por sensibilidad, bloqueo por OTP, límite de accesos, token de usuario ≠ token de descarga, revocación, expiración, enlace desconocido auditado, roles, validación de canal, retención, **trigger append-only** y **detección de manipulación** de la cadena |
