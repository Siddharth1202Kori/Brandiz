# 03 — SeoMaster Blueprint

> What we build, how, and in what order. Derived from [02-semrush-architecture.md](02-semrush-architecture.md) §9.
> Data sourcing (accounts, contracts, keys) is owned by the user: **DataForSEO**, **Google Search Console**, **a SERP API**. This doc defines how the system consumes them.
> Date: 2026-10-27 · Rev 2: 2026-10-28 — decisions D1–D6 locked (§12), free-tier hosting plan (§14), paid resources (§15).

---

## 1. Product goal & principles

**Goal:** Semrush-style SEO suite for SMBs/agencies: keyword research, domain/competitor analysis, backlinks, rank tracking, site audit, GSC insights. Built on bought data + own crawler. **Run on free tiers until revenue.**

| Principle | From Semrush evidence | Our rule |
|---|---|---|
| Thin gateways over data | per-tool gateways (`kwogw`, `dpa`) | One FastAPI router per tool family, each with its own prefix |
| Data is precomputed/cached | sub-second reports | Every provider call goes through a cache. Never call a provider twice for the same question within its TTL |
| Metering everywhere | limits in every response | Every report view checks and decrements quota. Every provider call is logged with its cost |
| One API style | Semrush has 4 (legacy) | REST + OpenAPI only |
| Observable | `server-timing`, `x-service`, tracing | Same headers from day 1 |
| Provider-agnostic | — | Tools talk to **interfaces**, never to DataForSEO directly. Swapping providers = new adapter |
| Free-tier aware | — | Every component has a known free-tier ceiling and a paid upgrade path (§14, §15) |

---

## 2. Tech stack (locked)

| Layer | Choice | Why |
|---|---|---|
| Backend language | **Python 3.12** (D1) | Strong data/crawl ecosystem |
| Frontend language | TypeScript | Required by the React UI kit |
| Repo | Monorepo: **uv** workspace (Python) + **pnpm** (web) | Two toolchains, one repo |
| API | **FastAPI** + Pydantic v2 | Typed REST, OpenAPI generated automatically |
| Type sharing | `openapi-typescript` generates the TS client from FastAPI's OpenAPI | One source of truth for request/response shapes |
| Web app | **React + Vite SPA**, TanStack Router/Query/Table | Same pattern as Semrush's `unified-dashboard`. Static build → free static hosting |
| UI kit | **Intergalactic `@semcore/*`** (D2, MIT) + its d3-based charts | Semrush look, data-dense tables |
| App DB | **PostgreSQL** (Neon free) + SQLAlchemy 2 + Alembic | Users, orgs, projects, plans, usage, settings |
| Analytics DB | **ClickHouse from day 1** (D3), self-hosted on the free VM | Rank history, GSC rows, audit pages, provider payload cache, cost ledger |
| Jobs | **Celery** + Celery Beat | Rank checks, crawls, GSC sync, provider pulls |
| Broker | Redis **on the free VM** (not Upstash, see §14.2) | Celery polls constantly |
| Cache / rate limits | **Upstash Redis** (free) | Report cache, single-flight locks, per-user rate limits |
| Crawler | **Scrapy** (+ optional `scrapy-playwright` for JS pages) | Site Audit |
| Auth | FastAPI + `authlib` (email + Google OAuth); JWT in httpOnly cookie | Google OAuth also grants GSC scope |
| Billing | Stripe (US) + Razorpay (IN) | Plans → entitlements |
| Observability | Sentry (free) + OpenTelemetry + web-vitals | Mirrors Semrush stack |
| Hosting | Netlify (web) · Render (API) · Neon (PG) · Upstash (cache) · Oracle Cloud Always Free VM (workers, broker, ClickHouse) | All free; details §14 |

---

## 3. System architecture

```
                         ┌───────────────────────────┐
 Browser ──HTTPS──────▶  │ Netlify: React SPA (static)│
     │                   └───────────────────────────┘
     │ /api/v1/...
     ▼
 ┌──────────────────────────────────────────────┐        ┌──────────────────┐
 │ Render (free web service)                     │──────▶ │ Neon Postgres    │
 │ FastAPI  routers: keywords | domains |        │        │ app state        │
 │ backlinks | rank | audit | gsc | projects |   │        └──────────────────┘
 │ billing | limits   → DAL (cache→meter→provider)│──────▶ ┌──────────────────┐
 └───────┬──────────────────────┬────────────────┘        │ Upstash Redis    │
         │ enqueue (TLS)        │ query (HTTPS)           │ cache, locks,    │
         ▼                      ▼                         │ rate limits      │
 ┌──────────────────────────────────────────────┐        └──────────────────┘
 │ Oracle Cloud Always Free VM (ARM, docker)     │
 │  Redis (Celery broker, TLS+ACL)               │
 │  Celery workers: rank-check | audit-crawl |   │──▶ DataForSEO · SERP API · GSC API
 │    gsc-sync | provider-fetch | refresh-stale  │
 │  Celery Beat (schedules)                      │
 │  Scrapy (spawned per crawl)                   │
 │  ClickHouse (analytics, HTTPS + password)     │
 │  Caddy (TLS termination)                      │
 └──────────────────────────────────────────────┘
```

**Request path (report view):**
`UI → FastAPI router → limits.check() → DAL.get(question) → Upstash hit? return : ClickHouse cache hit? return : provider adapter → normalize → ClickHouse → Upstash → meter → respond (+server-timing)`

---

## 4. Data Access Layer (the core)

### 4.1 Provider interfaces (`packages/providers`)

```python
from typing import Protocol


class KeywordProvider(Protocol):
    async def overview(
        self, kw: str, market: Market
    ) -> KeywordMetrics: ...  # volume, cpc, kd, intent, trend
    async def ideas(self, seed: str, market: Market, opts: IdeaOpts) -> Page[KeywordMetrics]: ...
    async def serp(self, kw: str, market: Market) -> SerpSnapshot: ...


class DomainProvider(Protocol):
    async def overview(
        self, domain: str, market: Market
    ) -> DomainOverview: ...  # traffic, keywords, history
    async def ranked_keywords(
        self, domain: str, market: Market, opts: PageOpts
    ) -> Page[RankedKeyword]: ...
    async def competitors(self, domain: str, market: Market) -> list[Competitor]: ...


class BacklinkProvider(Protocol):
    async def summary(
        self, target: str
    ) -> BacklinkSummary: ...  # authority, refdomains, follow/nofollow
    async def backlinks(self, target: str, opts: PageOpts) -> Page[Backlink]: ...
    async def ref_domains(self, target: str, opts: PageOpts) -> Page[RefDomain]: ...
    async def anchors(self, target: str, opts: PageOpts) -> Page[Anchor]: ...


class RankProvider(Protocol):
    async def check_positions(
        self, batch: list[RankCheck]
    ) -> list[RankResult]: ...  # daily tracking


class FirstPartyProvider(Protocol):  # GSC
    async def sites(self, user_id: str) -> list[GscSite]: ...
    async def search_analytics(self, site: str, q: GscQuery) -> list[GscRow]: ...
```

Models are Pydantic. Fields mirror Semrush fields seen in doc 02 §5 (`phrase, volume, cpc, keyword_difficulty, intents, trends, position, url, serp_features, traffic, traffic_cost, ...`).

### 4.2 Markets at launch (D6)

| Market | Code | DataForSEO `location_code` | Language |
|---|---|---|---|
| India | `in` | 2356 | en (hi later) |
| United States | `us` | 2840 | en |

`Market` is an enum. Adding a market = one row + plan-gating, no code change.

### 4.3 Provider → tool mapping (user sources; verify endpoints against provider docs)

| Tool | Primary | Complement |
|---|---|---|
| Keyword Overview | DataForSEO Labs (keyword overview) + Keywords Data (Google Ads volume) | SERP API for live SERP |
| Keyword Magic (ideas) | DataForSEO Labs (keyword ideas / related / suggestions) | — |
| Domain Overview / Organic | DataForSEO Labs (domain rank overview, ranked keywords, competitors) | — |
| Backlinks | DataForSEO Backlinks (summary, backlinks, refdomains, anchors, history) | — |
| Position Tracking | **SERP API** (D4) | adapter can point at DataForSEO SERP later |
| Site Audit | **Own crawler** (Scrapy) | Google PageSpeed API (free) for CWV |
| GSC Insights | **Google Search Console API** (OAuth, `searchanalytics.query`) | — |
| Keyword ↔ page blending | GSC clicks/impressions + DataForSEO volume | — |

### 4.4 Cache & cost control

Two cache tiers: **Upstash** (hot, small, TTL) → **ClickHouse** `provider_payloads` (durable, large). Upstash's 256 MB stays small; ClickHouse holds full payloads.

| Data type | Cache key | TTL |
|---|---|---|
| Keyword metrics | `kw:{market}:{normalized_kw}` | 30 days (volumes are monthly) |
| SERP snapshot | `serp:{market}:{device}:{kw}` | 24 h |
| Domain overview | `dom:{market}:{domain}` | 7 days |
| Ranked keywords page | `domkw:{market}:{domain}:{page}:{sort}` | 7 days |
| Backlink summary | `bl:{target}` | 7 days |
| Backlink lists | `bl:list:{target}:{type}:{page}` | 7 days |
| GSC rows | ClickHouse, incremental daily sync | n/a |

Rules:
- **Single-flight:** concurrent identical requests share one provider call (Upstash `SET NX` lock).
- **Store-then-serve:** normalized results persisted in ClickHouse so cache survives Redis eviction.
- **Cost ledger:** every provider call writes `provider_calls(provider, endpoint, cost_usd, org_id, cache_hit, latency_ms)` to ClickHouse. DataForSEO returns `cost` per task; store it.
- **Budget guard:** daily global and per-org spend caps; above cap → serve stale or queue.
- **Batching:** rank checks and keyword volumes batched (providers price per task).
- **Queue vs live:** provider "standard/queued" modes for scheduled jobs (cheaper); "live" only for interactive views.
- **Upstash budget:** ~16k commands/day on free tier (§14.2). One report view ≈ 3–5 commands → ~3k views/day ceiling. Metered in the ledger.

---

## 5. Modules (API prefixes)

| Module | Prefix | Endpoints (MVP) | Semrush analogue |
|---|---|---|---|
| auth/users | `/api/v1/auth` | login, OAuth callback, me | semrush2 |
| projects | `/api/v1/projects` | CRUD, members, connect GSC | projects / folders |
| limits | `/api/v1/limits` | `GET /me` → `[{name, used, max}]` | `/projects/api/limits` |
| keywords | `/api/v1/keywords` | `GET /overview?q&market`, `GET /ideas?seed&market&filters&page`, `GET /serp?q&market`, lists CRUD | kwogw / kmtgw / saved-keywords |
| domains | `/api/v1/domains` | `GET /overview?d&market`, `GET /organic?d&market&page`, `GET /competitors?d&market`, `GET /gap?d1&d2&market` | dpa |
| backlinks | `/api/v1/backlinks` | `GET /summary?t`, `GET /list?t&page`, `GET /refdomains?t`, `GET /anchors?t` | backlinks webapi2 |
| rank | `/api/v1/rank` | campaigns CRUD, `GET /campaigns/{id}/positions?from&to`, keywords add/remove | position-tracking |
| audit | `/api/v1/audit` | `POST /campaigns/{id}/run`, `GET /runs/{id}` (progress), `GET /runs/{id}/issues` | siteaudit |
| gsc | `/api/v1/gsc` | `GET /sites`, `GET /performance?site&dims&from&to`, `GET /opportunities` | (Semrush integrates GSC too) |
| billing | `/api/v1/billing` | checkout, portal, webhooks (Stripe, Razorpay) | back-wt / paysol |

Response envelope (one style):
```json
{ "data": {...}, "meta": { "limited": false, "cached": true, "source": "dataforseo", "fetched_at": "2026-10-27T00:00:00Z", "page": {"offset":0,"limit":100,"total":1234} } }
```
`meta.limited` mirrors Semrush `is_limited` (plan truncation).

---

## 6. Data model

### 6.1 Postgres (Neon) — app state, small, transactional

```
users(id, email, name, created_at)
orgs(id, name, plan_id, billing_provider, billing_customer_id)
org_members(org_id, user_id, role)
plans(id, name, limits_json)                 -- {"reports_per_day":10,"rank_keywords":500,"audit_pages":1000,...}
usage_counters(org_id, metric, period, used) -- metering
projects(id, org_id, domain, market, created_at)
gsc_connections(project_id, site_url, refresh_token_enc, scopes, last_sync_at)
keyword_lists(id, project_id, name) / keyword_list_items(list_id, market, keyword)
rank_campaigns(id, project_id, market, device, location_code, schedule)
rank_keywords(campaign_id, keyword, tags[])
audit_campaigns(id, project_id, start_url, max_pages, settings jsonb)
audit_runs(id, campaign_id, status, pages_crawled, started_at, finished_at, health_score)
```

### 6.2 ClickHouse (VM) — large, append-heavy, analytical

```sql
keyword_metrics     ReplacingMergeTree(fetched_at)  ORDER BY (market, keyword)
serp_snapshots      MergeTree  PARTITION BY toYYYYMM(taken_at)  ORDER BY (market, keyword, device, taken_at)
provider_payloads   ReplacingMergeTree(fetched_at)  ORDER BY key  TTL expires_at
provider_calls      MergeTree  PARTITION BY toYYYYMM(created_at) ORDER BY (provider, created_at)
rank_positions      MergeTree  PARTITION BY toYYYYMM(date) ORDER BY (campaign_id, keyword, date)
gsc_rows            MergeTree  PARTITION BY toYYYYMM(date) ORDER BY (project_id, date, query, page)
audit_pages         MergeTree  ORDER BY (run_id, url)
audit_issues        MergeTree  ORDER BY (run_id, issue_code, url)
```

Postgres stays well under Neon's free storage because every large table lives in ClickHouse.

Secrets: OAuth refresh tokens encrypted at rest (Fernet / envelope encryption, key in env). Provider credentials only in `.env` / platform secret settings, never in DB or client.

---

## 7. Background jobs (Celery)

| Task / queue | Trigger | Work | Notes |
|---|---|---|---|
| `rank-check` | Beat, daily per campaign | batch keywords → SERP API → find project domain → `rank_positions` | spread over the day to smooth cost |
| `audit-crawl` | user "Run" / weekly | spawn Scrapy crawl ≤ `max_pages`, robots.txt, per-host rate limit → pages → rules → issues → health score | progress in `audit_runs`; UI polls |
| `gsc-sync` | Beat, daily per connection | incremental `searchanalytics.query` → `gsc_rows` | GSC lags ~2–3 days; backfill 16 months on connect |
| `provider-fetch` | cache miss for heavy pulls | paginated pulls (all ranked keywords, all backlinks) | view gets first page live, rest queued |
| `refresh-stale` | Beat, nightly | re-fetch hot keys near TTL | only recently viewed entities |

Scrapy runs on Twisted, whose reactor can't restart inside a long-lived Celery worker. Each crawl therefore runs as a **subprocess** (`scrapy crawl audit -a run_id=…`), and the Celery task only supervises it. Concurrency: 1–2 crawls at once on the VM; `scrapy-playwright` only when a site needs JS rendering (memory-heavy).

Site Audit rules (MVP ~40): 4xx/5xx, redirect chains, missing/duplicate title & meta, missing/multiple H1, canonical issues, noindex, orphan pages, broken internal/external links, large images, slow pages, missing alt, mixed content, hreflang errors, sitemap/robots issues, thin content, Core Web Vitals via PageSpeed API.

---

## 8. Frontend structure (Vite SPA)

```
apps/web/src/routes/
  index.tsx               landing (prerendered)
  pricing.tsx
  app/
    dashboard/
    keywords/overview/    keywords/magic/   keywords/lists/
    domains/overview/     domains/organic/  domains/gap/
    backlinks/
    projects/$id/rank/    projects/$id/audit/   projects/$id/gsc/
    settings/billing/
```
- Global search bar (domain or keyword → right report), market selector (IN/US), project selector.
- Each report = widget grid; each widget = one API call via TanStack Query. Skeletons while loading; `meta.limited` → upsell banner.
- Cold-start handling: Render free API sleeps when idle (§14.2). SPA pings `/healthz` on load and shows a "waking up" state.
- Export CSV per table (metered by `export_limit`).

---

## 9. Monorepo layout

```
seomaster/
  apps/
    web/            React + Vite + @semcore (pnpm)
    api/            FastAPI app (routers, deps, auth)
    worker/         Celery app + Beat schedule
  packages/
    core/           Pydantic models, Market enum, normalizers
    providers/      Protocols + adapters (dataforseo, serp, gsc)
    db/             SQLAlchemy models, Alembic migrations, ClickHouse DDL
    crawler/        Scrapy project + audit rules
  infra/
    docker-compose.dev.yml     postgres, redis, clickhouse for local dev
    vm/compose.yml             Oracle VM: redis, clickhouse, worker, beat, caddy
    render.yaml                API service
    netlify.toml               web build
  pyproject.toml    uv workspace root
  pnpm-workspace.yaml
  docs/
```

---

## 10. Delivery plan

Detailed per-phase plans: [`Phases/`](../Phases/README.md).

| Phase | Scope | Exit criteria |
|---|---|---|
| **0. Foundation** (wk 1–2) | Monorepo, local docker (pg, redis, clickhouse), FastAPI + auth, orgs/projects, plans + limits + metering, DAL skeleton, ClickHouse schema + cost ledger, Celery wiring, Sentry/OTel, server-timing. All services run locally via docker-compose; the Oracle VM is not needed yet | Login, create project, `/limits/me` works locally. The always-on server (Oracle VM or fallback, §14) is required by Phase 4 |
| **1. Keywords** (wk 3–4) | DataForSEO adapter (keywords), Keyword Overview, Keyword Magic (filters: volume, KD, intent, include/exclude), lists, CSV export | Cache hit rate visible; cost per view logged |
| **2. Domains** (wk 5) | Domain Overview, Organic positions, Competitors, Keyword Gap | Same caching rules |
| **3. Backlinks** (wk 6) | Summary, list, refdomains, anchors, history chart | — |
| **4. GSC** (wk 7) | OAuth connect, 16-mo backfill, performance dashboard, opportunities (pos 4–20, high impressions low CTR), blend with DataForSEO volume | Daily sync stable |
| **5. Rank Tracking** (wk 8–9) | Campaigns, SERP API adapter, daily task, positions chart, visibility score, SERP features | Cost per keyword/day known |
| **6. Site Audit** (wk 10–11) | Scrapy crawler, 40 rules, health score, issue explorer, scheduled re-crawls, run diff | 1k-page site audited < 10 min on the VM |
| **7. Billing & polish** (wk 12–13) | Stripe (US) + Razorpay (IN) → entitlements, upsell surfaces, onboarding, PDF/CSV reports | Paid signup works end to end in both markets |
| Later | AI features (content brief, AI visibility like Semrush `ai-seo/*`), white-label reports, public API | — |

Python + ClickHouse from day 1 adds about one week to the original TS plan (two toolchains, VM setup).

---

## 11. What you need to provide

| Provider | Needed for | Env vars |
|---|---|---|
| DataForSEO | keywords, domains, backlinks | `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD` |
| SERP API | rank tracking | `SERP_API_PROVIDER`, `SERP_API_KEY` |
| Google Cloud OAuth client | login + GSC; scopes `openid email profile` + `webmasters.readonly` | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` |
| Neon | app DB | `DATABASE_URL` |
| Upstash | cache | `UPSTASH_REDIS_URL` (rediss://) |
| Oracle VM | broker + analytics | `CELERY_BROKER_URL` (rediss://, ACL user), `CLICKHOUSE_URL`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD` |
| Stripe / Razorpay | billing (phase 7) | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` |
| Sentry | errors | `SENTRY_DSN` |
| Email (Resend/Brevo) | verification, password reset | `EMAIL_API_KEY`, `EMAIL_FROM` |
| App | encryption, sessions | `APP_ENCRYPTION_KEY`, `AUTH_SECRET` |

Notes:
- Google OAuth consent screen needs a privacy policy and homepage on **your own domain**, plus Google verification before users beyond the test list can connect. `webmasters.readonly` is a *sensitive* (not *restricted*) scope, so no paid security assessment is required.
- Each platform holds its own secrets (Render env, VM `.env` with `chmod 600`). Nothing secret goes in the repo or the SPA bundle.

---

## 12. Decisions (locked 2026-10-28)

| # | Decision | Locked choice | Consequence |
|---|---|---|---|
| D1 | Language | **Python** (FastAPI + Celery + Scrapy); TS only for the web UI | Two toolchains; TS client generated from OpenAPI |
| D2 | UI kit | **Intergalactic `@semcore/*`** (MIT) | Semrush look. Don't copy Semrush branding/logo/colors-as-identity |
| D3 | Analytics store | **ClickHouse from day 1** | No free managed ClickHouse → self-host on VM (§14) |
| D4 | Rank-tracking source | **SERP API** | Behind `RankProvider`; can switch to DataForSEO SERP if cheaper |
| D5 | Hosting | **Free tiers**: Netlify, Render, Neon (or Supabase), Upstash, **+ Oracle Always Free VM** | VM added because free web hosts can't run Celery or ClickHouse (§14.2) |
| D6 | Markets at launch | **IN + US** | Two location codes; Stripe (US) + Razorpay (IN) |

---

## 13. Risks

| Risk | Mitigation |
|---|---|
| Provider cost blow-up | cache + single-flight + budget guard + per-plan metering from day 1 |
| Provider ToS on caching/resale | Check DataForSEO/SERP API reseller and caching terms before launch (user-owned) |
| Crawler abuse / blocks | robots.txt, per-host rate limit, identifiable UA, only verified project domains for deep crawls |
| GSC token handling | encrypt at rest, minimal scopes, revoke on disconnect |
| Data parity vs Semrush | Position as "accurate + affordable + GSC-blended". Don't claim index size |
| Free VM is a single point of failure | Nightly ClickHouse backup to Cloudflare R2 (free 10 GB); compose file makes rebuild one command; app degrades to "data refreshing" if VM down |
| Oracle reclaims idle Always Free VMs / ARM capacity unavailable in region | Workers keep CPU busy (not idle); try other availability domains; fallback = paid VM (§15) |
| Free tier limits change | All limits re-checked at each phase start; ledger shows usage vs ceiling |
| Render cold starts hurt UX | "Waking up" UI state; upgrade first when paying users arrive (§15) |

---

## 14. Free-tier hosting plan (D5)

### 14.1 Placement

| Component | Host | Free-tier ceiling (verify at signup) |
|---|---|---|
| React SPA | **Netlify** (free) | Static hosting, bandwidth/build-minute caps. Commercial use OK |
| FastAPI | **Render** free web service | 512 MB RAM, sleeps after ~15 min idle (30–60 s cold start), 750 free hours/month shared |
| Postgres | **Neon** free (or Supabase free) | ~0.5 GB storage on Neon. Supabase free pauses after a week of inactivity |
| Cache | **Upstash Redis** free | 500K commands/month (~16k/day), 256 MB |
| Workers, Beat, broker, Scrapy, ClickHouse | **Oracle Cloud Always Free** ARM VM | Up to 4 OCPU / 24 GB RAM, 200 GB block storage. Card needed for identity check |
| Backups | Cloudflare R2 free | 10 GB |
| Errors | Sentry Developer (free) | ~5k errors/month |
| Email | Resend or Brevo free | ~100–300 emails/day |

### 14.2 Why the extra VM (free-tier gaps found)

| Your pick | Problem | Fix |
|---|---|---|
| **Vercel** | Hobby plan is **non-commercial only**. A paid SEO SaaS breaks its terms | Use **Netlify** for the SPA. Vercel only with Pro (paid) |
| **Render** for workers | Render has **no free background workers or cron jobs**, only web services | Celery workers + Beat run on the Oracle VM |
| **Upstash** as Celery broker | Celery's Redis broker polls nonstop (~1 command/s per worker even when idle). That spends the 500K/month in about a week | Broker = Redis on the VM. Upstash only for cache/locks/rate limits |
| **ClickHouse** from day 1 | ClickHouse Cloud has only a 30-day / $300 trial, no permanent free tier | Self-host ClickHouse in docker on the VM (24 GB RAM is plenty) |

Note: your brief said Upstash = 10K requests/day. That was Upstash's old limit; the current free tier is 500K commands/month.

### 14.3 VM security baseline
- SSH key only, no password login; firewall opens 22 (your IP), 443 only.
- Caddy terminates TLS for ClickHouse HTTPS and the Redis TLS proxy; Redis ACL user + long password; ClickHouse non-default user, read/write split for API vs workers.
- Render has no static outbound IP on free tier, so IP allow-listing isn't possible: TLS + strong credentials are mandatory.
- Unattended security updates on; docker images pinned.

---

## 15. Paid resources — complete list, end to end

### 15.1 Must pay (no free path)

| Item | Why unavoidable | Cost model (verify live pricing) |
|---|---|---|
| **DataForSEO** | All keyword, domain and backlink data | Pay-as-you-go. ~$50 minimum deposit, no monthly fee. The old $100/month Backlinks minimum has been removed. Billed per task/row |
| **SERP API** | Rank tracking (D4) | Per search. Most vendors give a small free monthly quota for testing; production needs a paid plan or pay-as-you-go. DataForSEO SERP is usually the cheapest per check and uses the same deposit |
| **Domain name** | Your brand; Google OAuth verification needs a privacy-policy page on your own domain; email sending needs DNS records | ~$10–15/year (`.com`) |

### 15.2 Paid only when customers pay you

| Item | Cost model |
|---|---|
| **Stripe** (US customers) | No monthly fee; per-transaction % + fixed fee |
| **Razorpay** (IN customers) | No monthly fee; per-transaction % (Stripe India onboarding is restricted, so use Razorpay) |

### 15.3 Free now, card required for signup (no charge expected)

Oracle Cloud (identity check), Google Cloud project (GSC API and OAuth are free), Upstash (only if you upgrade), Cloudflare R2.

### 15.4 Becomes paid when you outgrow free tiers (upgrade order)

| Order | Trigger | Upgrade |
|---|---|---|
| 1 | First paying users notice cold starts | Render paid instance (always on) |
| 2 | Postgres nears free storage | Neon paid (usage-based) |
| 3 | Upstash > ~16k commands/day | Upstash pay-as-you-go (~$0.20 per 100K commands) with a budget cap |
| 4 | VM CPU/RAM/disk saturated, or Oracle reclaims it | Paid VM (Hetzner/DO) or ClickHouse Cloud |
| 5 | > ~5k errors/month | Sentry Team |
| 6 | Email volume > free cap | Resend/Brevo paid |

### 15.5 Optional paid (later features)

| Item | For |
|---|---|
| LLM API (Claude etc.) | AI content briefs, AI-visibility tracking |
| DataForSEO On-Page / extra APIs | Deeper audits without own crawl |
| Rotating proxies | **Not needed**: Site Audit crawls customers' own verified sites |

### 15.6 What a month costs in practice

- **Fixed cost during build and early launch:** about $1/month (the domain, spread over a year). Everything else is free tier.
- **Variable cost = provider usage**, controlled by cache + budget guard. Example for rank tracking: 10 projects × 100 keywords × 2 markets × 30 days = 60,000 checks/month, so price that against your SERP vendor's per-check rate before setting plan limits.
- Set the DataForSEO and SERP API spend caps in the app's budget guard **and** in the vendor dashboards, where supported.
