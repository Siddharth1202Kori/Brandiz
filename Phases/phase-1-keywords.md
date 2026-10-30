# Phase 1 — Keywords

**Weeks:** 3–4 · **Runs:** locally · **Online server:** not needed

## Goal
Keyword research tools on DataForSEO: Keyword Overview, Keyword Magic (ideas with filters), keyword lists, CSV export. First real provider adapter; proves cache + cost ledger with live money.

## Prerequisites
- Phase 0 exit criteria met
- DataForSEO account with deposit; credentials in `.env`

## Scope
**In:** DataForSEO adapter (keywords), overview, ideas, SERP preview, lists, export, intent, KD, trends.
**Out:** questions/AI clustering, multi-language (Hindi), bulk analysis > 100 keywords.

## 1. DataForSEO adapter (`packages/providers/dataforseo`)
- [x] HTTP client: `httpx.AsyncClient`, basic auth, timeouts, retry on 5xx/429 with jitter
- [x] Parse `status_code` per task (20000 = OK), raise typed errors otherwise
- [x] Read `cost` from each response → `provider_calls.cost_usd`
- [x] Market mapping: `in` → location 2356, `us` → 2840, language `en`
- [x] Endpoints (verify names/params in DataForSEO docs before coding):

| Use | Endpoint (v3) | Mode |
|---|---|---|
| Overview metrics | `dataforseo_labs/google/keyword_overview/live` | live |
| Search volume (bulk) | `keywords_data/google_ads/search_volume/task_post` | queued (cheaper) |
| Ideas | `dataforseo_labs/google/keyword_ideas/live` | live |
| Related | `dataforseo_labs/google/related_keywords/live` | live |
| Suggestions (contains seed) | `dataforseo_labs/google/keyword_suggestions/live` | live |
| Difficulty (bulk) | `dataforseo_labs/google/bulk_keyword_difficulty/live` | live |
| Intent | `dataforseo_labs/google/search_intent/live` | live |
| SERP preview | `serp/google/organic/live/advanced` (top 10) | live |

- [x] Recorded fixtures (sanitized JSON) for every endpoint → tests never call live API

## 2. Normalization (`packages/core`)
`KeywordMetrics`: `keyword, market, volume, cpc, competition, kd, intents[], trend[12], serp_features[], fetched_at, source`
- [x] Keyword normalizer: lowercase, trim, collapse spaces, NFC unicode
- [x] Missing values → `None`, never 0 (0 volume ≠ unknown)

## 3. Data
ClickHouse:
- [x] `keyword_metrics` (ReplacingMergeTree by `fetched_at`, ORDER BY `(market, keyword)`)
- [x] `serp_snapshots` (partition by month)
Postgres:
- [x] `keyword_lists`, `keyword_list_items`

## 4. API (`/api/v1/keywords`)
| Endpoint | Quota metric | Cache TTL |
|---|---|---|
| `GET /overview?q&market` | `reports_per_day` 1 | 30 d metrics, 24 h SERP |
| `GET /ideas?seed&market&mode=ideas\|related\|suggestions&filters&sort&page` | `reports_per_day` 1 + `keyword_ideas_rows` per page | 30 d |
| `GET /serp?q&market` | included in overview | 24 h |
| `GET/POST/DELETE /lists`, `POST /lists/{id}/items` | `keyword_lists` count | — |
| `GET /ideas/export.csv` | `exports_per_day` 1 | — |

Filters (applied server-side on cached full result): volume min/max, KD min/max, CPC min/max, intent, include words, exclude words, word count.
- [x] Plan truncation: free plan sees first N rows → `meta.limited=true`

## 5. Jobs
- [x] `fetch.keyword_volume_batch` — queued Google Ads volume for list items with stale volume
- [x] `maintenance.refresh_stale_keywords` (nightly, only keywords viewed in last 7 days)

## 6. Frontend
- [x] **Keyword Overview** page: volume card, KD gauge, CPC/competition, intent badges, 12-month trend chart, SERP top-10 table, "Add to list"
- [x] **Keyword Magic**: seed input, mode tabs (ideas/related/suggestions), filter bar, sortable `@semcore` data table with virtual scroll, bulk select → add to list, CSV export
- [x] **Lists** page: lists, items with metrics, remove, export
- [x] Global search: plain text → Keyword Overview
- [x] Upsell banner when `meta.limited`

## Tests
- Normalizer: fixtures → expected `KeywordMetrics` (snapshot tests)
- Adapter: error codes mapped, cost captured, retries bounded
- Second identical request = 0 provider calls (ledger asserts `cache_hit=true`)
- Filters on cached data correct; pagination stable

## Deliverables
DataForSEO keyword adapter, 3 keyword pages, lists, export, nightly refresh.

## Exit criteria
- [ ] Overview for "seo tools" in IN and US renders in < 2 s cold, < 300 ms cached
- [x] Cache hit rate and cost per view visible (simple admin page reading `provider_calls`)
- [x] Free-plan truncation + daily limit enforced
- [x] All adapter tests run on fixtures only

## Risks
| Risk | Mitigation |
|---|---|
| Ideas endpoints return thousands of rows → cost | Fetch with provider `limit`; paginate from ClickHouse; cap per plan |
| Volume differences between Labs and Google Ads | Store `source`; show one consistently (Labs) |
| India data sparse for long-tail | Show "no data" state, not zero |

## Your actions
- [ ] DataForSEO deposit; set a daily spend alert in their dashboard
- [x] Decide free-plan limits — defaults set, see Decisions below (adjust in `seed.py` + a migration)

## Decisions (build, 2026-10-30)
- **Report metering:** one `reports_per_day` per org per report per day. Re-opening, sorting, filtering, paging the same report is free. Overview + SERP of one keyword = one report.
- **Idea rows:** `keyword_ideas_rows` is a daily counter charged by high-water mark (rows already seen today are free). New cap `ideas_rows_per_report` limits rows visible per report.
- **Free plan:** 10 reports/day, 50 rows per report, 250 idea rows/day, 0 exports, 1 keyword list. Pro: 500 rows/report, 20 lists. Agency: 100 lists.
- **Fetch size:** ideas fetch 500 rows per report (≈ $0.06 on Labs), cached 30 days; filters/sort/paging run on that cached set.
- **Cache keys include the provider** (`kw:dataforseo:in:seo tools`) so fake and real data never mix.
- **Volume source:** Labs everywhere in reports; Google Ads queued tasks only fill list items (`source` stored per row).
- **List item metrics:** copied from ClickHouse `keyword_metrics` on add; unknown keywords filled by `fetch.keyword_volume_batch` (every 15 min).
- **Nightly refresh:** at most 50 keywords/night (`REFRESH_MAX_PER_RUN`) to bound cost; raise with traffic.
- **Fake provider switch:** `KEYWORD_PROVIDER_FAKE=true` forces demo data even with credentials.
- **Admin page:** `/admin/usage`, gated by `ADMIN_EMAILS` (empty = any user outside prod).
