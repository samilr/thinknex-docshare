# 4. Prototipo

## 4.1 Flujo elegido y por qué

Se implementó el **flujo completo de punta a punta**: compartir → notificar (o copiar el enlace) →
verificar al destinatario → ver, descargar o editar según el permiso → auditar, incluidos los caminos negativos. Es la cadena que entrega el
valor de negocio: implementar solo una parte (por ejemplo, el registro) no demostraría que el
documento se comparte **de forma segura**, que es lo difícil del problema.

| Capacidad | Estado | Dónde verlo |
|---|---|---|
| Compartir por email (SMTP real a Mailpit) | ✅ | `make demo` paso 2, http://localhost:8025 |
| Compartir por WhatsApp y SMS (simulados) | ✅ | `make demo` pasos 4 y 7, bandeja simulada `GET /api/v1/admin/inbox` |
| OTP, descarga y marca de agua | ✅ | `make demo` paso 3, `out/doc-003-compartido.pdf` |
| Enlace de ThinkNex Docs (copiar y enviar por cualquier medio) | ✅ | `make demo` paso 3b, portal: *Compartir → Enlace ThinkNex Docs* |
| Permisos Ver, Ver y descargar, Editar | ✅ | Visor `/s/{token}`, `out/doc-004-pagina-1.png`, tests `test_links.py` |
| Edición del archivo vivo por el destinatario | ✅ | Test `test_edit_works_on_live_file`, sección 4.3 |
| Expiración, límite de accesos y revocación | ✅ | Pasos 6 y 7, tests de integración |
| Política de sensibilidad (reglas) | ✅ | Pasos 4 y 5 |
| Sensibilidad asistida por LLM | ✅ opcional | `SENSITIVITY_LLM_ENABLED=true` + `ANTHROPIC_API_KEY` |
| Auditoría: quién, cuándo y por qué medio | ✅ | Paso 8, `GET /api/v1/audit?document_id=doc-003` |
| Integridad y append-only | ✅ | Paso 9, `GET /api/v1/audit/verify` |
| Retención de snapshots | ✅ | `make gc`, test `test_retention_purges_snapshot_but_keeps_hash` |
| **Portal web con login y roles** | ✅ | http://localhost:8080 (local) o la URL de Cloud Run |
| **Explorador tipo SharePoint** (bibliotecas, carpetas, subida, versiones, visor, personas con acceso) | ✅ | Portal → Documentos |
| Administración de usuarios y roles | ✅ | Portal → Usuarios (ADMIN) |
| Bandeja simulada (enlaces y OTP) | ✅ | Portal → Bandeja simulada (ADMIN) |
| Despliegue en GCP | ✅ | [06-despliegue-gcp.md](06-despliegue-gcp.md) |

## 4.2 Ejecución

Requisitos: Docker (con Compose v2), `make`, `curl` y `jq`. Para correr los tests: [`uv`](https://docs.astral.sh/uv/).

Los comandos respetan `APP_ENV` (`local` por defecto, `hybrid` o `gcp`; ver
[07-entornos.md](07-entornos.md)).

```bash
cp .env.example .env     # valores locales ficticios; make up lo hace si falta
make up                  # postgres, s3 (SeaweedFS), mailpit, document-api, share-api, web
make demo                # recorre los 9 pasos del flujo con curl
make test                # 106 tests: backend (unitarios + integración con Postgres real) + frontend
make e2e                 # prueba de humo Playwright sobre el portal (requiere `make up`)
make lint                # ruff + mypy --strict + eslint + prettier + tsc
make down                # o `make reset` para borrar también los datos
```

| URL | Qué es |
|---|---|
| **http://localhost:8080** | **Portal web** (SPA + proxy a la API, mismo origen) |
| http://localhost:8000/docs | Swagger de share-api (botón **Authorize**: `ana@thinknex.example` / `Demo-pass-2026`) |
| http://localhost:8001/docs | Swagger del DMS simulado (header `X-API-Key`, ver `.env`) |
| http://localhost:8025 | Bandeja de Mailpit: emails con enlace y OTP |
| http://localhost:8080/s/{token} | Visor del destinatario (el enlace llega por el canal o lo copia quien comparte) |

### Usuarios ficticios

| Usuario | Rol | Puede |
|---|---|---|
| `admin@thinknex.example` | ADMIN | Usuarios y roles, políticas, biblioteca completa, compartir, todos los envíos (revocar), bandeja simulada, retención |
| `ana@thinknex.example` | SHARER | Compartir, listar y revocar sus shares |
| `bruno@thinknex.example` | SHARER | Igual que Ana (para probar que no puede revocar lo de Ana) |
| `carla@thinknex.example` | AUDITOR | Consultar y verificar la auditoría |

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

1. Entrar como **ana** → *Documentos*. Elegir la biblioteca *Comercial* → carpeta *Certificados*:
   - **Subir** un PDF (arrastrar y soltar). Si contiene datos personales, se avisa.
   - Abrir un archivo: el **panel** muestra la vista previa con marca de agua "Vista interna", el
     historial de versiones (por ejemplo, `doc-001` en *Legal / Contratos* tiene v1 y v2), las
     **Personas con acceso** y la **Actividad**.
   - **Compartir** desde el panel `Certificado de cliente` (doc-006) con un email externo. La revisión
     de seguridad muestra RUT, teléfono y tarjeta enmascarados; hay que confirmar antes de enviar.
   - **Nueva versión:** subir un archivo con el mismo nombre ofrece publicarlo como versión nueva.
   - **Renombrar** desde el menú del archivo o su panel: la extensión no se edita, un nombre repetido
     en la carpeta se rechaza y la pestaña *Actividad* muestra «nombre anterior» → «nombre nuevo»
     con quién lo cambió.
2. Cerrar sesión y entrar como **admin** → *Bandeja simulada* → *Abrir como destinatario* →
   *Enviarme el código* → copiar el código desde la bandeja y escribirlo. Se abre el **visor**: páginas
   con marca de agua y, con el permiso por defecto, el botón *Descargar*.
3. **Enlace de ThinkNex Docs** (como **ana**): *Documentos → Marketing → Catálogo de productos 2026
   → Compartir → Enlace ThinkNex Docs*:
   - *Cualquiera con el enlace* + *Solo ver*: copiar el enlace y abrirlo en una ventana privada. Se ve
     el documento, pero **no hay botón Descargar** y la API responde 403 si se intenta.
   - Con un documento con datos personales (doc-006), *Cualquiera con el enlace* se bloquea: hay que
     usar *Persona específica*.
   - *Persona específica* + *Editar* (por ejemplo, el informe de *Operaciones*): el código llega a
     Mailpit; el destinatario ve la versión vigente y puede *Subir nueva versión*. En el panel del
     archivo aparece la versión nueva, subida por `destinatario:<email>`.
   - En *Personas con acceso*, **Nuevo enlace** invalida el anterior ("Enlace no disponible").
4. Como **admin** → *Políticas*: editar "Datos personales a externos" y quitar *Correo
   electrónico*. Un documento que solo tiene emails deja de pedir confirmación; con RUT sigue
   pidiéndola. También se pueden crear reglas, por ejemplo "Confidenciales nunca por WhatsApp"
   (Bloquear, clasificación Confidencial, medio WhatsApp). El AUDITOR ve la página en solo lectura.
   El admin también entra a *Documentos*: sube, edita (nombre y **clasificación**) y **elimina**
   archivos, y también puede compartirlos. Eliminar revoca los envíos activos del archivo.
5. Como **admin** → *Usuarios → (menú de Ana) → Actuar como este usuario*: el portal se ve como
   Ana, con un aviso "Actuando como…" y el botón *Volver a mi cuenta*. Lo que se haga queda a
   nombre de Ana con "vía admin@…" en la auditoría (ADR-0012). El *Resumen* lleva a cada pantalla
   al tocar sus indicadores, y el admin también ve *Auditoría*.
6. Como **admin** → *Usuarios* → *Nuevo usuario*. La contraseña temporal se muestra una sola vez y
   el nuevo usuario debe cambiarla al entrar.
7. Entrar como **carla** → *Auditoría*: banner "Cadena íntegra", filtro por `doc-006` y
   exportación a CSV. Aparecen `ACCESS_GRANTED`, `DOCUMENT_VIEWED`, `DOCUMENT_VERSION_UPLOADED`
   (actor destinatario) y `SHARE_LINK_ROTATED`.

### Alternativa por API (Swagger)

1. En http://localhost:8000/docs, **Authorize** con `ana@thinknex.example`.
2. `POST /api/v1/shares` con:
   ```json
   {"document_id": "doc-003", "recipient": {"name": "Pedro", "email": "pedro@auditora.example"},
    "channel": "EMAIL", "reason": "Auditoría Q3"}
   ```
   Para un enlace de solo lectura para cualquiera: `"channel": "LINK", "audience": "ANYONE",
   "permission": "VIEW", "recipient": null`. La respuesta trae `link` (solo esa vez).
3. Abrir el email en http://localhost:8025 (o la bandeja del portal), abrir el enlace, pedir el
   código y verificarlo. La API pública del visor está en `/api/v1/access/{token}` (sección
   *destinatario (público)* de Swagger).
4. **Authorize** con `carla@thinknex.example` y llamar `GET /api/v1/audit?document_id=doc-003`.

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
| `document-api/tests` (15) | API key, bibliotecas y carpetas, migas de pan, hash publicado = contenido, versiones, conflicto de nombre, **magic bytes**, límite de tamaño, nombre seguro, DOCX por estructura |
| `share-api/tests/unit` (47) | Detectores (RUT con dígito verificador, Luhn, solapamientos), matriz de política, **política de enlaces y permisos**, IA solo advierte, redacción antes del LLM, JWT con tipos, OTP ligado al share, marca de agua, **render de páginas a PNG**, hash canónico, redacción de logs, selección de adaptadores, secretos débiles rechazados |
| `share-api/tests/integration` (30) | Flujo E2E con el visor, 409/403 por sensibilidad, bloqueo por OTP, límite de accesos, revocación, expiración, roles, retención, **trigger append-only**, **detección de manipulación**; login, bloqueo de cuenta, **rotación de refresh con detección de reutilización**, cambio obligatorio de contraseña, desactivación inmediata; administración de usuarios, visibilidad por rol, bandeja e indicadores |
| `share-api/tests/integration` biblioteca (7) | Navegación, subida con hallazgos, conflicto y nueva versión, vista interna con marca de agua auditada, personas con acceso y actividad, roles, contenido inválido |
| `share-api/tests/integration` enlaces (8) | Enlace para cualquiera de solo lectura (páginas PNG, descarga 403), bloqueo con datos personales, reglas de audiencia y permiso, código por email, **edición del archivo vivo auditada como destinatario**, regeneración del enlace, límite de sesiones, sesión ligada a su envío |
| `web` Vitest (18) | Guardas de sesión y rol, login, contraseña temporal, asistente de compartir (incluido el enlace para cualquiera), **visor del destinatario** (solo lectura, código y edición, enlace no disponible), explorador, CSV, recuperación de chunks |
| `web/e2e` Playwright (3) | En el navegador contra el stack real: navegar, subir, abrir, compartir desde el panel, recibir, ver en el visor, descargar y auditar; **enlace de solo lectura para cualquiera y regeneración**; recuperación tras un despliegue |
