.DEFAULT_GOAL := help
SHELL := /bin/bash
SERVICES := services/document-api services/share-api
TEST_DATABASE_URL ?= postgresql+psycopg://thinknex:thinknex-local-dev@localhost:5433/share_test

# ----------------------------------------------------------------------------------------
# APP_ENV elige el entorno (ver docs/07-entornos.md):
#   local  → todo en Docker en localhost (Postgres, S3 compatible y Mailpit locales)
#   hybrid → contenedores en localhost conectados a la infraestructura real de GCP
#   gcp    → todo en Cloud Run (Cloud SQL, Cloud Storage, Secret Manager)
# Prioridad: línea de comandos (make up APP_ENV=gcp) > variable de entorno > .env > local
# ----------------------------------------------------------------------------------------
APP_ENV ?= $(shell sed -n 's/^APP_ENV=//p' .env 2>/dev/null)
override APP_ENV := $(if $(strip $(APP_ENV)),$(strip $(APP_ENV)),local)
ifeq ($(filter $(APP_ENV),local hybrid gcp),)
$(error APP_ENV="$(APP_ENV)" no es válido: usa local, hybrid o gcp)
endif

COMPOSE_local := docker compose -p thinknex-share -f docker-compose.yml -f compose.local.yml
COMPOSE_hybrid := docker compose -p thinknex-hybrid --env-file .env.hybrid -f docker-compose.yml -f compose.hybrid.yml
COMPOSE := $(COMPOSE_$(APP_ENV))

# Terraform con ADC o, si no existe, con un token temporal de la sesión de gcloud.
TF := terraform -chdir=$(CURDIR)/infra/terraform
TF_AUTH := [[ -f "$${CLOUDSDK_CONFIG:-$$HOME/.config/gcloud}/application_default_credentials.json" || -n "$${GOOGLE_OAUTH_ACCESS_TOKEN:-}" ]] || export GOOGLE_OAUTH_ACCESS_TOKEN=$$(gcloud auth print-access-token);

# Credenciales demo y URLs según el entorno (para demo y e2e).
CREDS_local := set -a; . ./.env; set +a;
CREDS_hybrid := set -a; . ./.env.hybrid; set +a;
CREDS_gcp := $(TF_AUTH) export BOOTSTRAP_ADMIN_EMAIL=$$($(TF) output -raw bootstrap_admin_email) BOOTSTRAP_ADMIN_PASSWORD=$$($(TF) output -raw admin_password) DEMO_USERS_PASSWORD=$$($(TF) output -raw demo_users_password);
WEB_URL_local := http://localhost:8080
WEB_URL_hybrid := http://localhost:8080
WEB_URL_gcp = $$($(TF) output -raw web_url_deterministic)

help: ## Muestra esta ayuda y el entorno activo
	@echo "Entorno activo: APP_ENV=$(APP_ENV)   (cambiar: make <target> APP_ENV=local|hybrid|gcp)"
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

.env:
	cp .env.example .env

# ------------------------------------------------------------------------ ciclo de vida
up: .env ## Levanta el entorno: local/hybrid en Docker (localhost); gcp despliega en Cloud Run
	@echo "▶ APP_ENV=$(APP_ENV)"
ifeq ($(APP_ENV),gcp)
	./scripts/deploy.sh
else ifeq ($(APP_ENV),hybrid)
	./scripts/env-hybrid.sh
	$(COMPOSE) up -d --build --wait --remove-orphans
else
	$(COMPOSE) up -d --build --wait --remove-orphans
endif

down: .env ## Detiene los contenedores (en gcp no apaga nada: ver gcp-destroy)
ifeq ($(APP_ENV),gcp)
	@echo "En gcp los servicios escalan a cero solos. Para eliminar la infraestructura: make gcp-destroy"
else
	$(COMPOSE) down
endif

reset: .env ## Solo local: detiene y BORRA volúmenes (BD y archivos locales)
ifneq ($(APP_ENV),local)
	$(error reset solo aplica a APP_ENV=local)
endif
	$(COMPOSE) down -v

logs: .env ## Logs de las APIs (Docker o Cloud Logging según APP_ENV)
ifeq ($(APP_ENV),gcp)
	gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name:"docshare-"' \
	  --freshness=15m --limit=60 --order=asc \
	  --format='value(timestamp,resource.labels.service_name,jsonPayload.msg,jsonPayload.path,jsonPayload.status,textPayload)'
else
	$(COMPOSE) logs -f share-api document-api
endif

status: .env ## Estado de los servicios y chequeo /ready
ifeq ($(APP_ENV),gcp)
	@gcloud run services list --format='table(metadata.name,status.url,status.conditions[0].status)' 2>/dev/null | grep -E 'NAME|docshare'
	@$(TF_AUTH) curl -s "$$($(TF) output -raw share_api_url)/ready" | jq .
else
	@$(COMPOSE) ps --format 'table {{.Service}}\t{{.Status}}'
	@curl -s http://localhost:8000/ready | jq . || echo "share-api no responde en :8000"
endif

# ------------------------------------------------------------------------ calidad
install: ## Instala dependencias locales (uv) de ambos servicios
	@for s in $(SERVICES); do (cd $$s && uv sync -q); done

lint: install ## ruff + mypy (servicios) y eslint + prettier + tsc (web)
	@for s in $(SERVICES); do (cd $$s && uv run ruff check . && uv run ruff format --check . && uv run mypy app) || exit 1; done
	cd web && npm ci --silent && npm run lint && npm run typecheck

test: install .env ## Tests unitarios + integración (siempre con el Postgres local)
	$(COMPOSE_local) up -d --wait postgres
	cd services/document-api && uv run pytest -q
	cd services/share-api && TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest -q
	cd web && npm ci --silent && npm test

web-dev: ## Portal en modo desarrollo (Vite :5173, proxy a share-api :8000)
	cd web && npm install --silent && npm run dev

e2e: .env ## Prueba de humo Playwright contra el entorno APP_ENV
	@$(CREDS_$(APP_ENV)) cd web && npx playwright install chromium >/dev/null && BASE_URL="$(WEB_URL_$(APP_ENV))" npm run e2e

demo: .env ## Recorre el flujo completo por API contra el entorno APP_ENV
	@$(CREDS_$(APP_ENV)) APP_ENV=$(APP_ENV) BASE_URL="$(WEB_URL_$(APP_ENV))" ./scripts/demo.sh

gc: .env ## Ejecuta la retención (vence shares y purga snapshots)
ifeq ($(APP_ENV),gcp)
	gcloud run jobs execute docshare-gc --region "$$($(TF_AUTH) $(TF) output -raw region)" --wait
else
	$(COMPOSE) exec share-api python -m app.jobs.gc
endif

ai-index: .env ## Sincroniza el índice de IA con todos los documentos (backfill)
ifeq ($(APP_ENV),gcp)
	gcloud run jobs execute docshare-indexer --region "$$($(TF_AUTH) $(TF) output -raw region)" --args=--backfill --wait
else
	$(COMPOSE) exec share-api python -m app.ai.worker --backfill
endif

# ------------------------------------------------------------------------ infraestructura GCP
gcp-bootstrap: ## GCP: APIs mínimas + bucket de estado (PROJECT_ID=... [REGION=...])
	./infra/gcp/bootstrap.sh $(PROJECT_ID) $(REGION)

gcp-plan: ## GCP: terraform plan con infra/terraform/demo.tfvars
	@$(TF_AUTH) $(TF) plan -var-file=demo.tfvars -out=tfplan

gcp-apply: ## GCP: aplica el plan revisado
	@$(TF_AUTH) $(TF) apply tfplan

gcp-deploy: ## GCP: construye, publica y despliega (igual que make up APP_ENV=gcp)
	./scripts/deploy.sh

gcp-destroy: ## GCP: elimina toda la infraestructura (evita costos)
	@$(TF_AUTH) $(TF) destroy -var-file=demo.tfvars

.PHONY: help up down reset logs status install lint test web-dev e2e demo gc gcp-bootstrap gcp-plan gcp-apply gcp-deploy gcp-destroy
