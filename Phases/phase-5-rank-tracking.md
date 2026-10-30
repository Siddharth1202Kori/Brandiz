# Phase 5 — Rank Tracking

**Weeks:** 8–9 · **Online server:** required

## Goal
Daily position tracking per project: campaigns, keywords, device and location, positions history, visibility score, SERP features, competitors — powered by the SERP API (D4).

## Prerequisites
- Phase 4 deployed stack running (worker + Beat)
- SERP API account; per-check price known

## Scope
**In:** campaigns, keyword import, daily checks (desktop/mobile), IN/US national + city locations, history chart, visibility, SERP features, up to 5 competitor domains, tags, alerts (email).
**Out:** hourly checks, local pack grid (map rank), AI Overview tracking (later).

## 1. SERP adapter (`RankProvider`)
- [ ] Provider chosen via `SERP_API_PROVIDER`; adapter per vendor (start with yours; DataForSEO SERP adapter as fallback)
- [ ] Request: keyword, location, language, device, depth = 100
- [ ] Parse organic results → positions for project domain + competitors; SERP features present (featured snippet, PAA, local pack, video, images, AI overview…)
- [ ] Use vendor's **queued/batch** mode for scheduled checks (cheapest); live only for "check now"
- [ ] Cost per check recorded in `provider_calls`

## 2. Data
Postgres: `rank_campaigns(id, project_id, market, device, location_code, schedule, competitors[])`, `rank_keywords(campaign_id, keyword, tags[], added_at)`
ClickHouse:
- [ ] `rank_positions(campaign_id, keyword, date, domain, position, url, serp_features[])` — PARTITION BY month
- [ ] `serp_snapshots` reused for full top-100 storage (compressed)

## 3. Jobs (`rank` queue)
| Task | Trigger | Detail |
|---|---|---|
| `rank.schedule_day` | Beat 00:05 UTC | split all active keywords into hourly slots (smooth cost + vendor rate) |
| `rank.check_batch` | per slot | submit batch → poll/callback → parse → write positions |
| `rank.retry_missing` | Beat 20:00 UTC | re-check keywords without today's result |
| `rank.alerts` | after day complete | position drop ≥ N / entered top 3 → email digest |

## 4. Metrics
- Position (null = not in top 100)
- **Visibility %** = Σ(CTR(position) × 1) / keywords, CTR curve table per device
- **Estimated traffic** = Σ CTR(position) × volume (volume from Phase 1 cache)
- Avg position, distribution buckets, ups/downs vs previous day

## 5. API (`/api/v1/rank`)
| Endpoint | Quota |
|---|---|
| `POST/GET/PATCH/DELETE /campaigns` | `rank_campaigns` |
| `POST /campaigns/{id}/keywords` (bulk, CSV) | `rank_keywords` total |
| `GET /campaigns/{id}/overview?from&to` | — |
| `GET /campaigns/{id}/positions?from&to&tags&page` | — |
| `GET /campaigns/{id}/competitors?from&to` | — |
| `POST /campaigns/{id}/check-now` | `rank_live_checks` (paid plans) |

## 6. Frontend
- [ ] Campaign wizard: location (IN/US + city search), device, keywords (paste/CSV/from list/from GSC), competitors
- [ ] Overview: visibility trend, estimated traffic, avg position, distribution, top movers
- [ ] Positions table: keyword, today, Δ1d, Δ7d, Δ30d, URL, SERP feature icons, sparkline
- [ ] Competitor comparison chart
- [ ] Tags filter; export CSV

## Tests
- Parser on fixture SERPs (domain match incl. subdomains, `www`)
- Visibility/traffic formulas
- Scheduler: N keywords spread across slots; retries only missing
- Quota: keyword cap per plan enforced on bulk add

## Exit criteria
- [ ] 7 consecutive days of unattended checks for a 100-keyword IN + US campaign
- [ ] Missing results < 1% after retry
- [ ] Cost per keyword/day recorded and ≤ plan budget assumption

## Risks
| Risk | Mitigation |
|---|---|
| Cost scales linearly with keywords × days | Plan caps; weekly-check option on free plan |
| SERP layout/vendor format changes | Fixture tests + Sentry alerts on parse errors |
| VM worker down on a day | `retry_missing` + gap marked "no data", not "not ranking" |

## Your actions
- [ ] SERP API plan with enough checks; set vendor spend alerts
- [ ] Decide keywords per plan (e.g. free 10 weekly, pro 500 daily)
