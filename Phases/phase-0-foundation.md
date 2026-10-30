# Phase 0 — Foundation

**Weeks:** 1–2 · **Runs:** locally (docker-compose) · **Online server:** not needed

## Goal
Working skeleton every later phase plugs into: monorepo, auth, orgs/projects, plans + limits + metering, Data Access Layer (DAL), ClickHouse schema + cost ledger, Celery wiring, observability. No SEO data yet.

## Prerequisites
- Docker Desktop, Python 3.12, `uv`, Node 20+, `pnpm`
- Google Cloud project with an OAuth client (for "Sign in with Google"), test users added
- Optional now: Neon + Upstash accounts (local docker replaces both)

## Scope
**In:** repo structure, local infra, auth, orgs, projects, plans, limits, DAL skeleton, provider interfaces (no adapters), ClickHouse DDL, Celery hello-task, Sentry, `server-timing`, CI, SPA shell with `@semcore`.
**Out:** any DataForSEO/SERP/GSC call, billing, deployment to free hosts (optional stretch).

## 1. Repo & tooling
- [ ] `git init`, `.gitignore` (**`.env` first**), `.env.example` with every var from doc 03 §11 (empty values)
- [ ] uv workspace: `apps/api`, `apps/worker`, `packages/{core,providers,db,crawler}`
- [ ] pnpm workspace: `apps/web`
- [ ] Ruff (lint+format), mypy (strict on `packages/core`, `packages/providers`), pytest + pytest-asyncio
- [ ] ESLint + Prettier + `tsc --noEmit` for web
- [ ] pre-commit hooks: ruff, mypy, secret scan (gitleaks)
- [ ] GitHub Actions: lint, typecheck, tests (Python + web) on every push

## 2. Local infra (`infra/docker-compose.dev.yml`)
| Service | Image | Port |
|---|---|---|
| postgres | postgres:16 | 5432 |
| redis | redis:7 | 6379 (broker + cache locally) |
| clickhouse | clickhouse/clickhouse-server (pinned) | 8123 / 9000 |
- [ ] `make dev` (or `just dev`): compose up + migrations + API + worker + web
- [ ] Healthchecks on all three services

## 3. Backend (FastAPI, `apps/api`)
- [ ] App factory, settings via `pydantic-settings` (reads `.env`)
- [ ] Middleware: request id, `server-timing` (total, db, cache, provider), `x-service: api`, CORS for SPA origin
- [ ] Error envelope + exception handlers; response envelope `{data, meta}` helper
- [ ] `GET /healthz` (DB, Redis, ClickHouse ping) — used by SPA wake-up check
- [ ] OpenAPI exported to `apps/web/src/api/openapi.json` on build → `openapi-typescript` client

### Auth (`/api/v1/auth`)
- [ ] Google OAuth login (authlib), scopes `openid email profile` only (GSC scope added in Phase 4)
- [ ] Email + password (argon2) with email verification token (email sender stubbed to console locally)
- [ ] Session = signed JWT in httpOnly, `Secure`, `SameSite=Lax` cookie; CSRF token for mutating requests
- [ ] `GET /me`, `POST /logout`
- [ ] Rate limit login endpoints (Redis)

### Orgs & projects (`/api/v1/projects`)
- [ ] Auto-create personal org on signup; roles `owner|member`
- [ ] Projects CRUD: `domain` (normalized, no scheme/www), `market` (`in|us`)
- [ ] Authorization dependency: user must belong to project's org

### Plans, limits, metering (`/api/v1/limits`)
- [ ] Seed plans: `free`, `pro`, `agency` with `limits_json` (reports_per_day, keyword_ideas_rows, rank_keywords, audit_pages, gsc_sites, exports_per_day, projects)
- [ ] `limits.check(org, metric, amount)` + `limits.consume(...)`, atomic (`UPDATE … WHERE used + n <= max RETURNING`)
- [ ] Period handling: daily / monthly reset by `period` key (e.g. `2026-11-02`, `2026-11`)
- [ ] `GET /limits/me` → `[{name, used, max, period}]`
- [ ] FastAPI dependency `require_quota("reports_per_day")`

## 4. Data layer
### Postgres (`packages/db`, Alembic)
Tables from doc 03 §6.1: `users, orgs, org_members, plans, usage_counters, projects` (+ empty `gsc_connections`, `keyword_lists`, `rank_*`, `audit_*` created in their phases).

### ClickHouse (`packages/db/clickhouse/*.sql`)
- [ ] Migration runner (ordered `.sql` files + `schema_migrations` table in ClickHouse)
- [ ] Create now: `provider_payloads`, `provider_calls` (others in their phases)
- [ ] Async client: `clickhouse-connect`

## 5. Data Access Layer (`packages/providers`)
- [ ] Protocols: `KeywordProvider, DomainProvider, BacklinkProvider, RankProvider, FirstPartyProvider` (doc 03 §4.1)
- [ ] Pydantic models in `packages/core`: `Market`, `Page[T]`, `PageOpts`, plus placeholders
- [ ] `DAL.get(key, ttl, fetch_fn, cost_meta)`:
  1. Redis hot cache → hit returns `meta.cached=true`
  2. ClickHouse `provider_payloads` (not expired) → warm Redis, return
  3. Single-flight lock (`SET key:lock NX PX 30000`); waiters poll result
  4. `fetch_fn()` → normalize → write ClickHouse + Redis → log `provider_calls`
- [ ] Budget guard: daily global + per-org spend cap (`settings.BUDGET_*`); over cap → stale data or `429 budget_exceeded`
- [ ] `FakeProvider` implementations for tests and UI dev

## 6. Worker (`apps/worker`)
- [ ] Celery app, broker = `CELERY_BROKER_URL`, result backend disabled (status lives in Postgres)
- [ ] Queues declared: `rank`, `audit`, `gsc`, `fetch`, `maintenance`
- [ ] Beat with one `heartbeat` task writing timestamp → shown in `/healthz`
- [ ] Task base class: Sentry, retry with backoff, structured logging

## 7. Frontend (`apps/web`)
- [ ] Vite + React + TS + TanStack Router/Query
- [ ] `@semcore/*` install, theme tokens, base layout (sidebar nav, top bar)
- [ ] Global search bar (UI only), market selector (IN/US, stored per user), project selector
- [ ] Pages: login, signup, verify email, dashboard (empty), projects list/create, limits widget
- [ ] Generated API client + auth guard + "API waking up…" state using `/healthz`
- [ ] Brand: own name/logo/colors — **not** Semrush's

## 8. Observability
- [ ] Sentry (API, worker, web) with release tags
- [ ] OpenTelemetry tracing API → worker (trace id propagated in task headers)
- [ ] Structured JSON logs with request id

## Tests
- Limits: concurrent consume never exceeds max (parallel test)
- DAL: cache hit/miss, single-flight (10 concurrent → 1 fetch), budget guard
- Auth: cookie flags, CSRF rejection, org isolation (user A can't read project of org B)
- Coverage target ≥ 80% on `packages/*`

## Deliverables
Monorepo, `make dev` one-command start, migrations, auth, projects, limits, DAL + FakeProvider, ClickHouse ledger, Celery heartbeat, SPA shell, CI green.

## Exit criteria
- [ ] Fresh clone → `make dev` → app running in < 10 min
- [ ] Sign up (email + Google), create project, see `/limits/me` in UI
- [ ] DAL test with FakeProvider shows cache hit + ledger row in ClickHouse
- [ ] CI green; no secrets in git history (gitleaks clean)

## Risks
| Risk | Mitigation |
|---|---|
| Two toolchains slow setup | One `make dev`; documented in README |
| `@semcore` learning curve | Build 3 base components first (table, card, chart wrapper) |
| Over-engineering DAL | Only the 4-step flow above; no plugins |

## Your actions
- [ ] Install Docker Desktop
- [ ] Create Google Cloud project + OAuth client (redirect `http://localhost:8000/api/v1/auth/google/callback`)
- [ ] Choose product name/brand for the UI
