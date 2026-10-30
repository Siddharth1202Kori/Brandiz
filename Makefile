.PHONY: help install infra-up infra-down migrate dev api worker beat web openapi test test-unit lint typecheck check

COMPOSE = docker compose -f infra/docker-compose.dev.yml

help: ## list targets
	@grep -E "^[a-z-]+:.*##" Makefile | sed "s/:.*##/ —/"

install: ## install Python + web dependencies
	uv sync
	pnpm install

infra-up: ## start postgres, redis, clickhouse (docker)
	$(COMPOSE) up -d --wait

infra-down: ## stop local datastores (data kept in volumes)
	$(COMPOSE) down

migrate: ## apply Postgres (alembic) + ClickHouse migrations
	uv run alembic -c packages/db/alembic.ini upgrade head
	uv run python -m seomaster_db.clickhouse

dev: install infra-up migrate ## one command: deps, datastores, migrations, then api+worker+beat+web
	uv run honcho -f Procfile.dev start

api: ## FastAPI on :8000 with reload
	uv run uvicorn seomaster_api.app:create_app --factory --reload --port 8000 --reload-dir apps --reload-dir packages

worker: ## Celery worker (all queues)
	uv run celery -A seomaster_worker.celery_app worker -Q maintenance,rank,audit,gsc,fetch --loglevel=INFO --pool=threads --concurrency=4

beat: ## Celery beat scheduler
	uv run celery -A seomaster_worker.celery_app beat --loglevel=INFO --schedule .celerybeat-schedule

web: ## Vite dev server on :5173
	pnpm --filter web dev

openapi: ## regenerate the typed web API client from FastAPI
	uv run python -W ignore -m seomaster_api.openapi > apps/web/src/api/openapi.json
	pnpm --filter web gen:api

test-unit: ## fast tests, no docker needed
	uv run pytest -m "not integration"

test: ## all tests (needs make infra-up)
	uv run pytest

lint: ## ruff + eslint
	uv run ruff check .
	uv run ruff format --check .
	pnpm --filter web lint

typecheck: ## mypy + tsc
	uv run mypy
	pnpm --filter web typecheck

check: lint typecheck test ## everything CI runs
