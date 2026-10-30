# Brandiz

Brandiz — Semrush-style SEO suite: keyword research, competitor analysis, backlinks, rank tracking, site audit and Google Search Console insights. Markets at launch: India + US.

- Architecture: [`docs/03-seomaster-blueprint.md`](docs/03-seomaster-blueprint.md)
- Delivery plan: [`Phases/`](Phases/README.md)

## Stack
Python 3.12 · FastAPI · Celery · Postgres · ClickHouse · Redis · React + Vite + Intergalactic (`@semcore/ui`) · uv + pnpm monorepo.

## Quick start (local)

Prerequisites: Docker Desktop, Python 3.12, [uv](https://docs.astral.sh/uv/), Node 20+, pnpm.

```bash
cp .env.example .env      # Google OAuth (login) + DataForSEO (keyword data; empty = demo data)
make dev                  # deps + datastores + migrations + api/worker/beat/web
```

Open http://localhost:5173 and sign up. Verification emails land in Mailpit: http://localhost:8025.

Without DataForSEO credentials (or with `KEYWORD_PROVIDER_FAKE=true`) keyword tools run on free deterministic demo data. `.env` is read when `make dev` starts: restart it after editing.

| Service | URL |
|---|---|
| Web app | http://localhost:5173 |
| API + docs | http://localhost:8000/docs |
| Health | http://localhost:8000/healthz |
| ClickHouse | http://localhost:8123 (user/pass `seomaster`) |

## Common commands

```bash
make help        # all targets
make test        # all tests (needs `make infra-up`)
make test-unit   # fast tests, no docker
make check       # lint + typecheck + tests (what CI runs)
make openapi     # regenerate typed web client after API changes
uv run python scripts/record_dataforseo.py   # record live DataForSEO responses (~$0.15) to diff with fixtures
```

## Layout

```
apps/api        FastAPI service (auth, projects, limits, reports)
apps/worker     Celery workers + Beat
apps/web        React SPA
packages/core       settings, markets, models, normalizers
packages/db         SQLAlchemy models, Alembic + ClickHouse migrations
packages/providers  provider interfaces + Data Access Layer (cache, single-flight, budget, ledger)
infra/          docker-compose for local datastores
```

## Rules
- Routers never call data providers directly — always through the DAL (`packages/providers/dal.py`).
- Every report is metered against plan limits; every provider call lands in the ClickHouse cost ledger.
- `.env` is never committed. Secrets live in `.env` locally and in platform settings in production.
