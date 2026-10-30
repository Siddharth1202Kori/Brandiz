# Phase 4 — Google Search Console (GSC)

**Week:** 7 · **Online server:** **required from here** (daily sync must run unattended)

## Goal
Connect a project to GSC, backfill 16 months, sync daily, show performance and opportunities, blend real clicks/impressions with DataForSEO volume. SeoMaster's differentiator.

## Prerequisites
- Phases 0–3 done
- Always-on server ready (Oracle Always Free VM or fallback, doc 03 §14): Redis broker, Celery worker + Beat, ClickHouse
- First deployment: SPA on Netlify, API on Render, Postgres on Neon, cache on Upstash
- Own domain with privacy policy + homepage (Google OAuth verification)

## Scope
**In:** OAuth connect (incremental scope), site picker, backfill, daily sync, performance dashboard, opportunities, keyword blending.
**Out:** URL Inspection API, indexing API, sitemaps submit (later).

## 1. Deployment (first time online)
- [ ] VM: docker compose (`infra/vm/compose.yml`): redis (TLS via Caddy, ACL user), clickhouse (HTTPS, non-default users), worker, beat, caddy
- [ ] VM hardening: SSH key only, firewall 22/443, unattended upgrades (doc 03 §14.3)
- [ ] Render: API service from `render.yaml`, env vars, `/healthz`
- [ ] Netlify: SPA build, `VITE_API_URL`, SPA redirect rule
- [ ] Neon: run Alembic migrations; Upstash: cache URL
- [ ] Nightly ClickHouse backup → Cloudflare R2
- [ ] Production Google OAuth redirect URIs added

## 2. OAuth & connection
- [ ] Incremental auth: request `https://www.googleapis.com/auth/webmasters.readonly` only on "Connect GSC" (`access_type=offline`, `prompt=consent`, `include_granted_scopes=true`)
- [ ] Store refresh token encrypted (Fernet, `APP_ENCRYPTION_KEY`) in `gsc_connections`
- [ ] `sites.list` → user picks property; match to project domain (`sc-domain:` or URL-prefix)
- [ ] Disconnect = revoke token at Google + delete row + keep or purge data (user choice)
- [ ] Handle `invalid_grant` (revoked) → mark connection broken, email user

## 3. Sync jobs (`gsc` queue)
| Task | Trigger | Detail |
|---|---|---|
| `gsc.backfill` | on connect | 16 months, day by day, dims `date,query,page,country,device`, `rowLimit=25000` + `startRow` paging |
| `gsc.sync_daily` | Beat, daily | last 5 days (re-fetch: data finalizes with ~2–3 day lag), upsert |
| `gsc.reconcile` | weekly | re-pull last 30 days to catch late corrections |
- [ ] Respect GSC API quotas (per-site and per-project QPS); throttle with token bucket per site
- [ ] Progress stored on connection (`backfill_progress`) for UI

## 4. Data (ClickHouse)
- [ ] `gsc_rows` (ReplacingMergeTree by `synced_at`, PARTITION BY month, ORDER BY `(project_id, date, query, page, country, device)`)
- [ ] Materialized views: daily totals per project; query-level 28-day aggregates

## 5. API (`/api/v1/gsc`)
| Endpoint | Purpose |
|---|---|
| `GET /connect` → redirect | start OAuth |
| `GET /sites` | properties for picker |
| `POST /projects/{id}/connection` | bind property |
| `GET /performance?project&from&to&dims&filters` | chart + table |
| `GET /opportunities?project` | see §6 |
| `GET /blend?project` | GSC queries + DataForSEO volume/KD |

## 6. Opportunity rules
| Type | Rule |
|---|---|
| Striking distance | avg position 4–20, impressions ≥ threshold |
| Low CTR | CTR below expected CTR for its position (curve table) |
| Decaying pages | clicks down > 30% vs previous 28 days |
| Cannibalization | same query, ≥ 2 pages with impressions |
| Untapped volume | DataForSEO volume high, GSC impressions low |

## 7. Frontend
- [ ] Project → "Connect Search Console" flow with property picker and backfill progress bar
- [ ] Performance: clicks/impressions/CTR/position chart, date compare, tables by query/page/country/device
- [ ] Opportunities: tabbed lists with suggested action text
- [ ] Keyword Overview badge: "Your site: position X, Y clicks (GSC)"

## Tests
- Token encryption round-trip; revoked token path
- Paging + upsert idempotent (re-run sync → same totals)
- Opportunity rules on fixture data

## Exit criteria
- [ ] Real property connected; 16-month backfill completes
- [ ] Daily sync runs 7 days unattended without errors (Sentry clean)
- [ ] Totals match GSC UI within rounding for same filters
- [ ] App live on free hosts end to end

## Risks
| Risk | Mitigation |
|---|---|
| OAuth verification delay (days–weeks) | Submit at start of Phase 4; use test users meanwhile |
| GSC rows anonymized/limited for rare queries | Explain in UI; totals from date-only query |
| VM down → no sync | Beat catches up missed days on restart (sync window ≥ 5 days) |

## Your actions
- [ ] Buy domain, publish privacy policy + homepage
- [ ] Submit OAuth consent screen for verification
- [ ] Create Oracle (or fallback) server; Render, Netlify, Neon, Upstash, R2 accounts
