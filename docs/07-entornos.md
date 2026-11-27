# 7. Entornos: una variable, tres perfiles (`APP_ENV`)

Una sola variable decide dónde corre la plataforma y contra qué infraestructura:

| `APP_ENV` | Contenedores | Base de datos | Archivos | Secretos | Correos |
|---|---|---|---|---|---|
| **`local`** (por defecto) | Docker en localhost | Postgres local | S3 local (SeaweedFS) | `.env` (valores ficticios) | Mailpit local |
| **`hybrid`** | Docker en localhost | **Cloud SQL** (vía Cloud SQL Auth Proxy) | **Cloud Storage** | **Secret Manager** (`.env.hybrid`) | Mailpit local |
| **`gcp`** | **Cloud Run** | Cloud SQL | Cloud Storage | Secret Manager | Bandeja simulada (o Resend) |

El portal muestra en el encabezado una insignia **Local / Híbrido / GCP**, para saber siempre
contra qué datos se está trabajando.

**IA en cada perfil** ([08-ia.md](08-ia.md)):

| `APP_ENV` | Embeddings | Claude |
|---|---|---|
| `local` | De prueba (`EMBEDDINGS_PROVIDER=fake`), sin red | Real si `.env` tiene `ANTHROPIC_API_KEY` |
| `hybrid` | Vertex AI (credenciales ADC del usuario) | Real (`ANTHROPIC_API_KEY`) |
| `gcp` | Vertex AI (cuenta de servicio) | Real (secreto `anthropic-api-key`) |

Los fragmentos no se comparten entre perfiles: cada base tiene su índice (`make ai-index`).

## Cómo se elige

Prioridad (de mayor a menor):
1. Línea de comandos: `make up APP_ENV=hybrid`
2. Variable de entorno de la terminal: `export APP_ENV=gcp`
3. El archivo `.env`: `APP_ENV=local`
4. Si no se indica nada: `local`

## Los mismos comandos en los tres perfiles

| Comando | `local` / `hybrid` | `gcp` |
|---|---|---|
| `make up` | Construye y levanta en Docker (en `hybrid` antes genera `.env.hybrid`) | Construye, publica y despliega en Cloud Run (`scripts/deploy.sh`) |
| `make down` | Detiene los contenedores | No apaga nada: escala a cero solo (`make gcp-destroy` elimina todo) |
| `make status` | Contenedores y `/ready` | Servicios de Cloud Run y `/ready` público |
| `make logs` | Logs de Docker | Cloud Logging |
| `make demo` | Flujo por API contra localhost | Flujo por API contra la URL pública |
| `make e2e` | Playwright contra localhost | Playwright contra la URL pública |
| `make gc` | Retención dentro del contenedor | Ejecuta el Cloud Run Job `docshare-gc` |
| `make ai-index` | Backfill del índice de IA dentro del contenedor | Ejecuta el Cloud Run Job `docshare-indexer --backfill` |

`make test` siempre usa el Postgres local, sin importar `APP_ENV`.

## Cómo funciona por dentro

- **Código:** share-api y document-api leen `APP_ENV` y completan sus valores por defecto según el
  perfil (`app/core/config.py` y `app/config.py`). Por ejemplo, el almacenamiento es S3 en local y
  Cloud Storage en hybrid y gcp. **Una variable explícita siempre gana** sobre el perfil.
- **Docker Compose:** `docker-compose.yml` es la base común (apps y Mailpit). `compose.local.yml`
  agrega Postgres y S3 locales. `compose.hybrid.yml` agrega el **Cloud SQL Auth Proxy** y monta en
  solo lectura las credenciales ADC del usuario para Cloud Storage.
- **Terraform:** define `APP_ENV=gcp` en los servicios y jobs de Cloud Run.

## Perfil `hybrid`: requisitos y precauciones

```bash
gcloud auth login
gcloud auth application-default login   # credenciales que usan el proxy y las apps locales
make up APP_ENV=hybrid                  # genera .env.hybrid y levanta en localhost:8080
```

- `scripts/env-hybrid.sh` arma `.env.hybrid` (permisos 600, **nunca se versiona**) con los nombres
  de recursos de `terraform output` y los secretos de Secret Manager. La conexión a la base pasa por
  el proxy local (`cloud-sql-proxy:5432`), autenticado con IAM.
- **Se trabaja sobre los datos reales del ambiente en la nube:** los usuarios, documentos, envíos y
  auditoría son los mismos que ven los evaluadores. Úsalo para depurar, no para hacer pruebas
  destructivas.
- Los enlaces que se envían en este modo apuntan a `http://localhost:8080`.
- `local` y `hybrid` usan los mismos puertos: antes de cambiar de perfil hay que bajar el anterior
  (`make down APP_ENV=local`).

## Agregar un perfil nuevo (por ejemplo, `staging`)

1. Agregar el valor a `AppEnv` y a `PROFILE_DEFAULTS` en ambos servicios.
2. Si corre en Docker, crear `compose.staging.yml`. Si es en la nube, crear otro `*.tfvars` con
   otro `name_prefix`.
3. Agregar sus variables `COMPOSE_staging`, `CREDS_staging` y `WEB_URL_staging` en el Makefile.
