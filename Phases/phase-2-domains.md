# Phase 2 — Domains (Competitive Analysis)

**Week:** 5 · **Runs:** locally · **Online server:** not needed

## Goal
Domain Overview, Organic Positions, Competitors and Keyword Gap — Semrush's `dpa` equivalents — on DataForSEO Labs.

## Prerequisites
- Phase 1 done (adapter base, keyword normalization, cache rules)

## Scope
**In:** domain overview, organic ranked keywords, top pages, competitors, keyword gap (2–3 domains), traffic history.
**Out:** paid/ads research, traffic analytics (clickstream), subdomain/subfolder drill-down (later).

## 1. Adapter additions (verify endpoint names in docs)
| Use | Endpoint (v3) |
|---|---|
| Overview (traffic, keyword counts, ETV) | `dataforseo_labs/google/domain_rank_overview/live` |
| History | `dataforseo_labs/google/historical_rank_overview/live` |
| Ranked keywords | `dataforseo_labs/google/ranked_keywords/live` |
| Top pages | `dataforseo_labs/google/relevant_pages/live` |
| Competitors | `dataforseo_labs/google/competitors_domain/live` |
| Keyword gap | `dataforseo_labs/google/domain_intersection/live` |

## 2. Normalization
- [ ] Domain normalizer: strip scheme, `www.`, path, port; IDN → punycode; reject IPs/localhost
- [ ] Models: `DomainOverview(organic_keywords, organic_traffic, traffic_cost, positions_dist{1-3,4-10,11-20,21-50,51-100}, history[])`, `RankedKeyword(keyword, position, url, volume, traffic, traffic_pct, kd, serp_features)`, `Competitor(domain, common_keywords, overlap_pct, traffic)`
- [ ] Label traffic as **estimated** everywhere

## 3. Data (ClickHouse)
- [ ] `domain_overviews` (ReplacingMergeTree, `(market, domain)`)
- [ ] `domain_ranked_keywords` (ORDER BY `(market, domain, fetched_at, position)`) — stores full pulls for paging/filtering

## 4. API (`/api/v1/domains`)
| Endpoint | Quota | TTL |
|---|---|---|
| `GET /overview?d&market` | 1 report | 7 d |
| `GET /organic?d&market&filters&sort&page` | 1 report + rows | 7 d |
| `GET /pages?d&market&page` | 1 report | 7 d |
| `GET /competitors?d&market` | 1 report | 7 d |
| `GET /gap?d1&d2[&d3]&market&type=missing\|weak\|shared\|untapped` | 1 report | 7 d |
| `GET /organic/export.csv` | 1 export | — |

- [ ] First page live; remaining pages via `fetch.domain_ranked_keywords` task (doc 03 §7 `provider-fetch`)

## 5. Frontend
- [ ] **Domain Overview**: KPI cards, traffic history chart, positions distribution bar, top keywords (10), top pages (10), top competitors (5) — each widget = own query (parallel loads, like Semrush)
- [ ] **Organic Positions**: full table, filters (position range, volume, KD, intent, URL contains), export
- [ ] **Competitors**: table + overlap bubble/scatter chart
- [ ] **Keyword Gap**: 2–3 domain inputs, tabs missing/weak/shared/untapped, add to list
- [ ] Global search: input looks like domain → Domain Overview

## Tests
- Domain normalizer edge cases (`HTTPS://WWW.Example.com/path?x` → `example.com`, IDN)
- Gap set logic against fixtures
- Background pagination completes and table reflects all rows

## Exit criteria
- [ ] Overview for a large IN and US domain renders all widgets
- [ ] Organic table with 10k+ rows filters/sorts in < 500 ms (ClickHouse)
- [ ] Keyword Gap correct on fixture domains
- [ ] Ledger shows cost per domain report

## Risks
| Risk | Mitigation |
|---|---|
| Huge domains (millions of keywords) | Cap pull per plan (e.g. 10k rows), `meta.limited` |
| Traffic estimates disputed by users | "Estimated" label + method tooltip; GSC (Phase 4) gives real numbers for own sites |

## Your actions
- [ ] Pick 3–5 test domains (IN + US) for QA and demos
