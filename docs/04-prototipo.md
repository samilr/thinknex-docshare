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
| **Portal web con login y roles** | ✅ | http://localhost:8080 (local) o la URL de Cloud Run |
| Administración de usuarios y roles | ✅ | Portal → Usuarios (ADMIN) |
| Bandeja simulada (enlaces y OTP) | ✅ | Portal → Bandeja simulada (ADMIN) |
| Despliegue en GCP | ✅ | [06-despliegue-gcp.md](06-despliegue-gcp.md) |

## 4.2 Ejecución

Requisitos: Docker (con Compose v2), `make`, `curl` y `jq`. Para correr los tests: [`uv`](https://docs.astral.sh/uv/).

```bash
cp .env.example .env     # valores locales ficticios; make up lo hace si falta
make up                  # postgres, s3 (SeaweedFS), mailpit, document-api, share-api, web
make demo                # recorre los 9 pasos del flujo con curl
make test                # 77 tests: backend (unitarios + integración con Postgres real) + frontend
make e2e                 # prueba de humo Playwright sobre el portal (requiere `make up`)
make lint                # ruff + mypy --strict + eslint + prettier + tsc
make down                # o `make reset` para borrar también los datos
```

| URL | Qué es |
|---|---|
| **http://localhost:8080** | **Portal web** (SPA + proxy a la API, mismo origen) |
| http://localhost:8000/docs | Swagger de share-api (botón **Authorize**: `ana@demo-corp.example` / `Demo-pass-2026`) |
| http://localhost:8001/docs | Swagger del DMS simulado (header `X-API-Key`, ver `.env`) |
| http://localhost:8025 | Bandeja de Mailpit: emails con enlace y OTP |
| http://localhost:8080/s/{token} | Página del destinatario (el enlace llega por el canal) |

### Usuarios ficticios

| Usuario | Rol | Puede |
|---|---|---|
| `admin@demo-corp.example` | ADMIN | Usuarios y roles, todos los envíos (revocar), bandeja simulada, retención |
| `ana@demo-corp.example` | SHARER | Compartir, listar y revocar sus shares |
| `bruno@demo-corp.example` | SHARER | Igual que Ana (para probar que no puede revocar lo de Ana) |
| `carla@demo-corp.example` | AUDITOR | Consultar y verificar la auditoría |

Contraseñas locales: ana, bruno y carla usan `DEMO_USERS_PASSWORD` (por defecto `Demo-pass-2026`);
el ADMIN usa `BOOTSTRAP_ADMIN_PASSWORD` (por defecto `Admin-demo-2026`). En la nube las genera
Terraform (ver el README).

### Documentos del DMS simulado

| ID | Clasificación | Qué demuestra |
|---|---|---|
| doc-001 | CONFIDENTIAL | Contrato con RUT de empresa y de persona. WARN hacia externos |
| doc-002 | CONFIDENTIAL | Liquidación con RUT, cuenta bancaria y email. WARN hacia externos |
| doc-003 | INTERNAL | Sin datos personales. ALLOW: el flujo feliz |
| doc-004 | PUBLIC | Catálogo. ALLOW |
| doc-005 | RESTRICTED | BLOCK hacia externos y WARN hacia internos |
| doc-006 | INTERNAL | RUT, teléfono y tarjeta de prueba. WARN hacia externos |

## 4.3 Probar el flujo en el portal

1. Entrar como **ana** → *Documentos* → *Compartir* `doc-006` con un email externo. La revisión de
   seguridad muestra RUT, teléfono y tarjeta enmascarados; hay que confirmar antes de compartir.
2. Cerrar sesión y entrar como **admin** → *Bandeja simulada* → *Abrir como destinatario* →
   *Enviar código* → copiar el código desde la bandeja → *Verificar y descargar* (PDF con marca de
   agua).
3. Como **admin** → *Usuarios* → *Nuevo usuario*. La contraseña temporal se muestra una sola vez y
   el nuevo usuario debe cambiarla al entrar.
4. Entrar como **carla** → *Auditoría*: banner "Cadena íntegra", filtro por `doc-006` y
   exportación a CSV.

### Alternativa por API (Swagger)

1. En http://localhost:8000/docs, **Authorize** con `ana@demo-corp.example`.
2. `POST /api/v1/shares` con:
   ```json
   {"document_id": "doc-003", "recipient": {"name": "Pedro", "email": "pedro@auditora.example"},
    "channel": "EMAIL", "reason": "Auditoría Q3"}
   ```
3. Abrir el email en http://localhost:8025 (o la bandeja del portal), abrir el enlace, pedir el
   código, verificar y descargar.
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
| `share-api/tests/unit` (33) | Detectores (RUT con dígito verificador, Luhn, solapamientos), matriz de política, IA solo advierte, redacción antes del LLM, JWT con tipos, OTP ligado al share, marca de agua, hash canónico, redacción de logs, selección de adaptadores, secretos débiles rechazados |
| `share-api/tests/integration` (30) | Flujo E2E, 409/403 por sensibilidad, bloqueo por OTP, límite de accesos, revocación, expiración, roles, retención, **trigger append-only**, **detección de manipulación**; login, bloqueo de cuenta, **rotación de refresh con detección de reutilización**, cambio obligatorio de contraseña, desactivación inmediata; administración de usuarios, visibilidad por rol, bandeja e indicadores |
| `web` Vitest (8) | Guardas de sesión y rol, login, contraseña temporal, asistente de compartir (WARN exige confirmación, BLOCK impide), CSV |
| `web/e2e` Playwright (1) | Recorrido completo en el navegador contra el stack real |
