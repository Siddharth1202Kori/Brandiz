# Finding Ledger — Semrush RE

Tags: [OBS] observed · [INF] inferred · [EXT] external · [UNK] unknown
Bundle: `docs/evidence/phase-a-bundle.json` (6 records)

## Phase A — public surface (2026-10-27)

| # | Finding | Tag | Evidence |
|---|---|---|---|
| A1 | Webpack, content-hashed chunks under `/__static__/webpack/`; legacy `/static/index.<hash>.js` coexists | OBS | ev_6d9784fe…, ev_3f4b0262… |
| A2 | React runtime fingerprint in `mf_widgets` | OBS (medium) | ev_3f4b0262… |
| A3 | Module Federation remotes `<app>-V<major>/<exposed>`: `shake-sidebar-V1/{optimize,brief,generate}`, `csat-feedback-V1/{init,widget}`, `growth-plan-improvements-V1/mount`, `sunset-banner-V1/mount`, `paysol-user-billing-information-V1/mount`, `paysol-widgets-V3/{MiniPricingWidget,QuickUpgradeWidget,QuickPurchaseWidget,ContactWidget,CustomPlanWidget,SubscribeWidget}` — registered in `init_component_provider` + `base` | OBS | ev_3f4b0262… |
| A4 | Remotes versioned by major in name → independent deploy per team, shell pins major | INF | A3 |
| A5 | `/jsi18n/` = Django JavaScriptCatalog → Django shell | INF (high) | ev_6d9784fe… |
| A6 | Endpoint `/back-wt/v1/billing_subscription` (fetch) — path-prefixed backend namespace + version | OBS | ev_3f4b0262… |
| A7 | First-party beacons: `POST /olaf/init`, `POST /smrwv/v1/webvitals`, `POST /_sentry/api/195/envelope/` (Sentry tunneled through own domain) | OBS | ev_d5f8c1b4… |
| A8 | Sentry with `sentry-trace`/`traceparent`/`baggage` → distributed tracing FE→BE | OBS/INF | ev_3f4b0262… |
| A9 | Doc headers: `via: 1.1 google`, `server: nginx`, `x-service: index`, `server-timing: service;dur, backend;dur`, `sm-log-id`, `x-logging-id`, `alt-svc: h3` | OBS | ev_d5f8c1b4… + curl -I |
| A10 | Edge = Google Cloud HTTPS LB (HTTP/3) → nginx → named service router (`x-service`) → backend | INF (high) | A9 |
| A11 | GCP Cloud Functions us-east4 (`gtm_monitoring`) | OBS | ev_d5f8c1b4… |
| A12 | Marketing stack: GTM + server-side GTM via OWOX BI (`streaming.bi.owox.com`), GA4 custom dims `semrush_product_name`, `semrush_team`, `is_bot`; Google Ads CCM; CookieHub consent; Intercom messenger; Amplitude (+session replay); SpeedCurve LUX | OBS | ev_d5f8c1b4…, ev_3f4b0262… |
| A13 | `static.semrush.com/ajst/ajst.js`, `ref-code-script/2.4.0/ref.js` (affiliate/referral attribution) | OBS | ev_d5f8c1b4… |
| A14 | Marketing pages: 0 client routes → server-rendered | OBS | ev_127404… |
| A15 | Source maps not fetched yet | UNK | — |

## Phase B — logged-in app (2026-10-27)
Sources: REA ev_4a0e8289… (inspect_web_page, SEO Dashboard), ev_2f108825… (analyze_web_bundle, 110 scripts, www+static origins), ev_79a823c8… (shell-only bundle); CDP shape recorder → `phase-b-api-shapes.json` (343 calls, 6 tool pages, values stripped).

| # | Finding | Tag |
|---|---|---|
| B1 | Tool apps on `static.semrush.com`: `remote-integrations/<app>-V<n>/` (MF 2.0, `mf-manifest.json`), `unified-dashboard` (Vite/Rolldown + TanStack + semcore), `semrush-navigation`, `siteaudit`, `intergalactic` | OBS |
| B2 | Source maps: 16 requested, all fetch_failed | OBS |
| B3 | Product route map (~45 routes incl. ai-seo/*) | OBS |
| B4 | `x-service` values: semrush2, analytics.{overview,keywordoverview,keywordmagic,backlinks}, kwogw.v2, kmtgw.v2, mini-kwogw.v2, back-wt, recommendation, position-tracking, site_audit_index, tools.my_reports | OBS |
| B5 | JSON-RPC 2.0 gateways (`kwogw`, `kmtgw`, `dpa/rpc`, `competitors/rpc`, `backlink_audit/rpc`) with `params.apiKey`, `userId` | OBS |
| B6 | Backlinks `webapi2` REST envelope exposes `base_time, exec_time, third_party_time, is_limited` | OBS |
| B7 | Newer services under `/apis/v4-raw/<svc>/api/v0/` (folders, saved-keywords) | OBS |
| B8 | GraphQL at `/my_reports/graphql` (`SidebarRecentReports`) | OBS |
| B9 | Entitlement/limit payloads fetched by every tool | OBS |
| B10 | Backlink history monthly since 2013 | OBS |
| B11 | Go + ClickHouse/Cassandra/Postgres/Kafka, GCP/K8s, petabyte scale | EXT (job posts) |
| B12 | Intergalactic = open-source MIT design system `@semcore/ui` | EXT |
