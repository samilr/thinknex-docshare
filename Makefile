.DEFAULT_GOAL := help
SERVICES := services/document-api services/share-api
TEST_DATABASE_URL ?= postgresql+psycopg://thinknex:thinknex-local-dev@localhost:5433/share_test

help: ## Muestra esta ayuda
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

.env:
	cp .env.example .env

up: .env ## Construye y levanta todo el stack (espera a que esté healthy)
	docker compose up -d --build --wait

down: .env ## Detiene el stack (conserva datos)
	docker compose down

reset: .env ## Detiene el stack y BORRA volúmenes (BD y archivos)
	docker compose down -v

logs: .env ## Sigue los logs de las APIs
	docker compose logs -f share-api document-api

install: ## Instala dependencias locales (uv) de ambos servicios
	@for s in $(SERVICES); do (cd $$s && uv sync -q); done

lint: install ## ruff + mypy en ambos servicios
	@for s in $(SERVICES); do (cd $$s && uv run ruff check . && uv run ruff format --check . && uv run mypy app) || exit 1; done

test: install .env ## Tests unitarios + integración (levanta solo Postgres)
	docker compose up -d --wait postgres
	cd services/document-api && uv run pytest -q
	cd services/share-api && TEST_DATABASE_URL=$(TEST_DATABASE_URL) uv run pytest -q

demo: ## Recorre el flujo completo contra el stack levantado
	./scripts/demo.sh

gc: ## Ejecuta el job de retención (vence shares y purga snapshots)
	docker compose exec share-api python -m app.jobs.gc

.PHONY: help up down reset logs install lint test demo gc
