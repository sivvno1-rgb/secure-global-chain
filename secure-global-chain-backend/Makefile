COMPOSE ?= docker compose

.PHONY: up down build logs migrate seed test dev seed-local

## Bring the full mesh up (build images first)
up:
	$(COMPOSE) up -d --build

## Stop the mesh (add ARGS=-v to drop data volumes)
down:
	$(COMPOSE) down $(ARGS)

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f api

## Apply DB migrations inside the running api container
migrate:
	$(COMPOSE) exec api alembic upgrade head

## Load idempotent demo data inside the running api container
seed:
	$(COMPOSE) exec api python -m sgc.seed

## Run the test suite locally (no services needed)
test:
	pytest

## Run the API locally with DEV auth on (no Keycloak needed)
dev:
	SGC_DEV_AUTH=true uvicorn sgc.main:app --reload --app-dir src

## Seed a local SQLite db for exploring without Docker
##   make seed-local        # then: make dev (same SGC_DATABASE_URL)
seed-local:
	SGC_DATABASE_URL=sqlite+aiosqlite:///./demo.db python -m sgc.seed --create-tables
