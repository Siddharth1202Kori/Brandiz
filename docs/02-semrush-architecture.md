# 02 — Semrush Architecture Breakdown

> Built from REA evidence (Phase A public + Phase B logged-in, 2026-10-27) per method in [01-reverse-engineering-approach.md](01-reverse-engineering-approach.md).
> Ledger: [evidence/ledger.md](evidence/ledger.md) · REA bundle: `evidence/phase-a-bundle.json` · API shapes (values stripped): `evidence/phase-b-api-shapes.json`
> Tags: **[OBS]** observed · **[INF]** inferred · **[EXT]** external public source · **[UNK]** unknown

---

## 1. One-screen summary

```
Browser
  │  HTTP/3
  ▼
Google Cloud HTTPS LB  (via: 1.1 google)                         [OBS]
  ▼
nginx edge/router  ── routes by URL prefix → named service        [OBS/INF]
  │                   (response header x-service = service name)
  ├─ semrush2            Django monolith: page shells, /jsi18n/, auth, accounts   [OBS/INF]
  ├─ analytics.*         per-report page services (overview, keywordoverview…)    [OBS]
  ├─ kwogw.v2 / kmtgw.v2 / mini-kwogw.v2   keyword gateways (JSON-RPC)            [OBS]
  ├─ dpa/rpc             domain analytics gateway (JSON-RPC)                      [OBS]
  ├─ backlinks/webapi2   backlink REST API                                         [OBS]
  ├─ apis/v4-raw/<svc>/api/v0   newer microservices (folders, saved-keywords)      [OBS]
  ├─ back-wt, recommendation, position-tracking, site_audit_index, tools.my_reports [OBS]
  └─ my_reports/graphql  GraphQL island                                           [OBS]
        ▼
  Data plane: ClickHouse / Cassandra / Postgres / Kafka on GCP + K8s, Go services  [EXT]
        ▲
  Offline pipelines: crawlers, SERP collectors, clickstream → precomputed indexes   [INF]

Frontend: Django HTML shell + React micro-frontends
  ├─ static.semrush.com/remote-integrations/<app>-V<major>/  (Module Federation)  [OBS]
  ├─ static.semrush.com/<tool-app>/  (per-tool SPA, e.g. unified-dashboard on Vite/Rolldown + TanStack) [OBS]
  └─ shared design system: Intergalactic (@semcore/ui, MIT)                         [OBS+EXT]
```

Core idea: **thin per-product gateways over precomputed analytical databases**. UI is a federation of independently deployed React apps glued by a Django shell.

---

## 2. Edge & routing

| Fact | Tag | Evidence |
|---|---|---|
| `via: 1.1 google` on every first-party response → Google Cloud external HTTPS LB | OBS | curl -I, `phase-b-api-shapes.json` |
| `alt-svc: h3`, responses served over HTTP/3 | OBS | protocol `h3` in shapes |
| `server: nginx` behind LB | OBS | headers |
| `x-service: <name>` names the upstream (`semrush2`, `kwogw.v2`, `analytics.overview`, `back-wt`, `recommendation`, `position-tracking`, `site_audit_index`, `tools.my_reports`) | OBS | shapes `infra` |
| `server-timing: service;dur, backend;dur`, `x-service-response-time`, `sm-log-id`, `x-logging-id` → per-request tracing/log correlation | OBS | ev_d5f8c1b4… |
| Single host `www.semrush.com`, path prefix → service. No CORS/subdomain sprawl; cookies shared | INF | all API on www |
| GCP Cloud Functions (us-east4) for small jobs (`gtm_monitoring`) | OBS | ev_d5f8c1b4… |

**Pattern:** path-prefix gateway. Each team owns a prefix (`/kwogw/`, `/dpa/`, `/siteaudit/api/`, `/apis/v4-raw/<svc>/`) and its service is named in `x-service`.

---

## 3. Frontend architecture

### 3.1 Shell (Django) [OBS/INF]
- HTML for each tool route (`/analytics/overview/`, `/siteaudit/`, …) rendered server-side; `x-service` of page = `analytics.<tool>` / `semrush2`.
- Shell scripts at `/__static__/webpack/` (Webpack, content-hashed): `runtime`, `base`, `header`, `footer`, `sentry`, `init_searchbar_api`, `init_folders_api`, `init_component_provider`, `observer_limit_options`, `track_billing_info_usage`, `mf_widgets`.
- `/jsi18n/` (served by `semrush2`) = Django `JavaScriptCatalog` → Django monolith confirmed. [INF high]
- `__static__/manifest.<hash>.json` fetched on each page → runtime asset/remote manifest.

### 3.2 Micro-frontends (Module Federation) [OBS]
Served from `static.semrush.com/remote-integrations/<name>-V<major>/` with `remoteEntry.js` + `mf-manifest.json` (MF 2.0 manifest).

| Remote | Exposes | Purpose |
|---|---|---|
| `search-bar-V1` | `Component`, `client_api` | global domain/keyword search bar |
| `project-selector-V1` | `Component`, `public_api` | project picker |
| `paysol-widgets-V3` | `MiniPricingWidget`, `QuickUpgradeWidget`, `QuickPurchaseWidget`, `SubscribeWidget`, `CustomPlanWidget`, `ContactWidget` | monetization/upsell |
| `paysol-user-billing-information-V1` | `mount` | billing info |
| `shake-sidebar-V1` | `optimize`, `brief`, `generate` | ContentShake AI writing sidebar |
| `csat-feedback-V1` | `init`, `widget` | in-app surveys |
| `recsystem-widget-V1` | — | recommendations ("you might also like") |
| `growth-plan-improvements-V1`, `sunset-banner-V1` | `mount` | growth experiments, deprecation banners |

Major version in folder name → shell pins a major, team ships minors freely. [INF]

### 3.3 Per-tool SPAs [OBS]
- `static.semrush.com/unified-dashboard/assets/*-<hash>.js` — chunk names `rolldown-runtime`, `route-index`, `route-*`, `tanstack`, `semcore`, `react`, `projectSetupSchema`, `googleSettingsQueryOptions`, `AnimatePresence` → **Vite (Rolldown) + React + TanStack Router/Query + Intergalactic + motion lib + schema validation**.
- `static.semrush.com/siteaudit/i18n/messages_en.<hash>.json` → Site Audit is its own SPA with own i18n bundle.
- `semrush-navigation/static/<build>/{header,sidebar,runtime}.js` → global nav is its own deployable.
- Legacy `/static/index.<hash>.js` still present → older build generation coexists. [OBS]

### 3.4 Product route map (from bundle, ev_2f108825…) [OBS]
`analytics/{overview, organic, ranks, toppages, backlinks, refdomains/report, comparedomains, keywordgap, gap/backlinks/report, keywordoverview, keywordmagic, keywordmanager/{list,audit}}`, `siteaudit/campaign`, `tracking`, `seo/:id`, `backlink_audit/:id`, `link_building/:id`, `on-page-seo-checker/:id`, `seo-content-template/:id`, `topic-research/:id`, `swa/checker/:id`, `sensor`, `ai-seo/{overview, brand-performance, competitor-research, narrative-drivers, perception, prompt-research, questions}`, `ai-marketing-workflow`, `/google-services`, `/setup`.

### 3.5 Design system [OBS+EXT]
`semcore` chunk + `intergalactic` assets → **Intergalactic** (`@semcore/ui`), Semrush's open-source React design system (MIT, 56–70+ components, 14+ chart types). [EXT: developer.semrush.com/intergalactic, github.com/semrush/intergalactic]

### 3.6 Source maps [OBS]
16 requested, all `fetch_failed` → not publicly served.

---

## 4. API layer

### 4.1 Styles in use (four generations)
| Style | Example | Tag |
|---|---|---|
| **JSON-RPC 2.0** gateways | `POST /kwogw/v2/webapi`, `/kmtgw/v2/webapi`, `/mini-kwogw/v2/webapi`, `/dpa/rpc`, `/analytics/competitors/rpc`, `/backlink_audit/rpc/?baMethod=` | OBS |
| **REST-ish GET** per widget | `GET /analytics/backlinks/webapi2/overview/{init,counters,ascore,anchors,historical,competitors,refdomains-ascore,…}?key&target&target_type` | OBS |
| **Versioned microservice REST** | `/apis/v4-raw/folders/api/v0/folders/selector-list`, `/apis/v4-raw/saved-keywords/api/v0/{user/limits,list/all,keyword/check-presence}`, `/back-wt/v1/billing_subscription`, `/recommendation/api/v2/get/`, `/projects/api/limits/` | OBS |
| **GraphQL** | `/my_reports/graphql` (op `SidebarRecentReports`) | OBS |

### 4.2 Auth model
- Session cookie on `www.semrush.com` (single origin). [INF]
- Data RPCs carry `params.apiKey` / query `key` — a **per-user API key injected into page**, so the same backend serves web UI and the paid public Semrush API. [OBS shape / INF purpose]
- RPC params also carry `userId`. [OBS]

### 4.3 Response envelopes
- JSON-RPC: `{jsonrpc, id, result}`.
- Backlinks webapi2: `{status, is_limited, base_time, exec_time, third_party_time, data}` — exposes **backend query timing** and **plan-limit truncation flag**. [OBS]
- Paginated lists: `{target, caps:{...feature flags}, total, limit, offset, data:[...]}`. [OBS]

### 4.4 Limits & entitlements are first-class API
Every tool fetches its quota before data:
- `kwogw/kmtgw` result: `max_updates, remaining_updates, allow_historical_data, has_ai_seo, trial_status, user_type`.
- `/projects/api/limits/` → `limits:[{name, used, max}]`.
- `saved-keywords/user/limits` → `total_keywords_limit, keyword_updates_used/limit`.
- dpa → `exportLimit, isHistoryAllowed, isPLAAllowed, isTrialUser`.
- Shell: `observer_limit_options`, `track_billing_info_usage`, `billing_subscription`. [OBS]

→ **Central entitlement service + per-gateway metering** (each report view decrements `remaining_updates`). [INF]

---

## 5. Per-tool breakdown

| Tool | Page service | Data calls | Response domain model (keys) | Tag |
|---|---|---|---|---|
| **Domain Overview** | `analytics.overview` | `dpa/rpc` (≈8 methods) | organic rows: `phrase, position, previousPosition, volume, cpc, keywordDifficulty, traffic, trafficCost, trafficPercent, url, serpFeatures, intents, trends, crawledTime`; history: `organicPositions*, adwordsPositions*, intent{Commercial,Informational,Navigational,Transactional}{Positions,Traffic,TrafficCost}, aiOverviewPositions, date`; backlinks summary: `authorityScore, backlinks, referringDomains, referringIPs, follow/nofollow, naturalness, linkPower`; AI: `ai_visibility, cited_pages, mention_stats` | OBS |
| **Keyword Overview** | `analytics.keywordoverview` | `kwogw.v2` (≈13 calls) | `phrase, volume, difficulty`; SERP rows `domain, url, position, kind, features`; `intents`; `history`; `total_volume`; competitors | OBS |
| **Keyword Magic** | `analytics.keywordmagic` | `kmtgw.v2`, `mini-kwogw.v2`, saved-keywords | `keywords, groups (topic clusters), count, total_volume, total_difficulty, rows_count, database` | OBS |
| **Backlinks** | `analytics.backlinks` | `backlinks/webapi2/*` (≈20 widget endpoints), `competitors/rpc`, `backlink_audit/rpc` | counters by link type (`follow, nofollow, sponsored, ugc, text, image, form, frame`), `ip, ipclassc`, anchors (`first_seen, last_seen`), monthly historical keyed by epoch since **2013** | OBS |
| **Site Audit** | `site_audit_index` | `siteaudit/api/campaigns/seolist`, `siteaudit/api/system-status` | campaigns list; separate SPA + i18n; crawl runs async (UNK details — no campaign in account) | OBS/UNK |
| **Position Tracking** | `position-tracking` | `projects/api/limits` | project-scoped; data calls not seen (no campaign) | OBS/UNK |
| **SEO Dashboard / Projects** | `unified-dashboard` SPA | folders API, `projectSetupSchema`, Google settings (GSC/GA integration) | project = folder; Google services connect | OBS |
| **ContentShake / AI** | MF `shake-sidebar-V1` | UNK | — | OBS/UNK |

Global per page: `search-bar/api/search(/save, /tld)`, `recommendation/api/v2/get`, `my_reports/api/v1/lite-order`, billing, `jsi18n`.

---

## 6. Backend & data plane

| Layer | Finding | Tag |
|---|---|---|
| Languages | Python/Django monolith (`semrush2`) for shell, auth, accounts | INF high |
| | Go for data services/gateways | EXT (job posts) |
| Storage | ClickHouse (analytics), Cassandra, Postgres, Kafka, Consul, ZooKeeper; Vertica mentioned once | EXT |
| Infra | GCP, Kubernetes, Docker, GitLab CI, Ansible | EXT + OBS (GCP LB/Functions) |
| Scale | petabytes across hundreds of servers | EXT |
| Query model | Report endpoints return fast (sub-second, `exec_time` exposed) → **precomputed per-database (`db=in`, `us`, …) indexes**, not live crawling | INF |
| Data freshness | `crawledTime` per keyword row; backlink `first_seen/last_seen`; monthly historical snapshots | OBS |
| Regional DBs | `db` param + `region, searchEngine, currencies` in dpa result → one keyword/SERP DB per country | OBS/INF |
| Async jobs | Site Audit, Position Tracking, Backlink Audit (`percent`, `isToxicScoreUpdating`, `lastRerunDate`) → job-queue workers updating status | OBS/INF |

### Inferred data pipelines [INF]
1. **SERP collector** → per-country keyword SERPs (positions, features, AI overview) → ClickHouse → Domain/Keyword Overview, Organic Research.
2. **Keyword volume model** (clickstream + Google Ads data) → `volume, cpc, comp, difficulty, intents`.
3. **Backlink crawler** → link graph (ascore, refdomains, anchors, link types) → backlinks webapi2.
4. **Project crawlers** (on demand): Site Audit crawler, Position Tracking daily SERP checks.
5. **LLM/AI visibility** collectors → `ai_visibility, mention_stats, cited_pages` (AI SEO toolkit).

---

## 7. Observability & growth stack [OBS]
- Sentry (tunneled via `/_sentry/api/195/envelope/`), with `traceparent`/`baggage` distributed tracing.
- RUM: in-house `smrwv` → `POST /smrwv/v1/webvitals` (session keys `smrwv_session_id/start/page_count`) + SpeedCurve LUX.
- Product analytics: Amplitude + session replay; first-party `olaf/init`.
- Marketing: GTM, server-side GTM via OWOX BI, GA4 with dims `semrush_product_name`, `semrush_team`, `is_bot`; Google Ads CCM; CookieHub consent; Intercom; affiliate `ref.js`.

---

## 8. Unknowns (next probes if needed)
| UNK | How to resolve |
|---|---|
| JSON-RPC method names per gateway | record `method` string (non-sensitive) in next pass |
| Site Audit crawl lifecycle, WebSocket/polling | create a small audit campaign, observe |
| Position Tracking data API | create a tracking campaign |
| GraphQL schema scope | observe `my_reports/graphql` ops on My Reports page |
| ContentShake/AI backend (LLM provider) | open shake sidebar, observe calls |
| Exact entitlement service | trace `observer_limit_options` with `trace_javascript_semantics` |

---

## 9. SeoMaster mapping (what to copy vs replace)

| Semrush part | Copy the pattern | SeoMaster choice |
|---|---|---|
| Path-prefix gateway + `x-service` + `server-timing` | ✅ | Single domain, reverse proxy (Caddy/nginx/Traefik), per-service prefix, emit `server-timing` |
| Django shell + micro-frontends | ⚠️ too heavy for MVP | One Next.js/Vite React app, route-split per tool; add Module Federation only when >3 teams |
| Per-tool gateway (kwogw, dpa) | ✅ | One "BFF" per tool family: keywords, domains, backlinks, audits |
| JSON-RPC/REST/GraphQL mix | ❌ legacy accretion | Pick one: REST + OpenAPI (or tRPC) |
| Entitlements in every response | ✅ | Central `limits` service, metered per report view |
| ClickHouse for analytical reads | ✅ | ClickHouse (or Postgres+Timescale at MVP) |
| Own SERP/keyword/backlink data | ❌ can't replicate at start | Buy: DataForSEO / SERP API / Google Ads Keyword Planner / GSC; own crawler only for Site Audit |
| Async job workers (audit, tracking) | ✅ | Queue (Redis/BullMQ, Celery, or Temporal) + progress endpoint |
| Intergalactic | ✅ usable (MIT) | Or shadcn/ui + Recharts |
| Observability (Sentry tunnel, RUM) | ✅ | Sentry + OpenTelemetry + web-vitals |

**Bottom line:** Semrush = (huge proprietary precomputed datasets) × (thin per-tool gateways) × (federated React UI) × (metering everywhere). SeoMaster can match the architecture early; data depth must be bought then grown.

---

### Sources [EXT]
- [Semrush job post: Senior Golang/ClickHouse Data Engineer (Red Team)](https://startup.jobs/senior-golang-developer-clickhouse-data-engineer-red-team-semrush-inc-8768462)
- [Builtin listing, same role](https://www.builtincolorado.com/job/senior-golang-developer-clickhouse-data-engineer-red-team/10238270)
- [Intergalactic design system](https://developer.semrush.com/intergalactic/)
- [@semcore/ui on npm](https://www.npmjs.com/@semcore/ui)
