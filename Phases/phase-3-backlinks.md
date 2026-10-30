# Phase 3 — Backlinks

**Week:** 6 · **Runs:** locally · **Online server:** not needed

## Goal
Backlink analytics on DataForSEO Backlinks API: summary, backlink list, referring domains, anchors, history, new/lost.

## Prerequisites
- Phase 2 done (domain normalizer)
- DataForSEO Backlinks API access confirmed on your account

## Scope
**In:** summary, backlinks, referring domains, anchors, history chart, new/lost, competitor comparison (up to 3).
**Out:** backlink audit/toxicity scoring, disavow file, link-building outreach (later).

## 1. Adapter additions (verify in docs)
| Use | Endpoint (v3) |
|---|---|
| Summary | `backlinks/summary/live` |
| Backlinks list | `backlinks/backlinks/live` |
| Referring domains | `backlinks/referring_domains/live` |
| Anchors | `backlinks/anchors/live` |
| History | `backlinks/history/live` |
| New/lost timeline | `backlinks/timeseries_new_lost_summary/live` |
| Compare | `backlinks/bulk_ranks/live`, `backlinks/bulk_backlinks/live` |

- [ ] Target types: domain, subdomain, exact URL (`target` param + `include_subdomains`)
- [ ] Use provider filters/order (`dofollow`, `first_seen`) to keep rows paid ≤ rows shown

## 2. Normalization
`BacklinkSummary(rank, backlinks, ref_domains, ref_ips, dofollow, nofollow, broken, new_30d, lost_30d)` · `Backlink(source_url, source_domain, source_rank, target_url, anchor, dofollow, first_seen, last_seen, is_lost)` · `RefDomain(...)` · `Anchor(text, backlinks, ref_domains)`
- [ ] Our authority = provider `rank` (0–1000) rescaled to 0–100; label as "SeoMaster Authority (from provider rank)"

## 3. Data (ClickHouse)
- [ ] `backlink_summaries`, `backlink_rows`, `ref_domain_rows`, `anchor_rows`, `backlink_history` — ORDER BY `(target, fetched_at, …)`

## 4. API (`/api/v1/backlinks`)
| Endpoint | Quota | TTL |
|---|---|---|
| `GET /summary?t&scope` | 1 report | 7 d |
| `GET /list?t&filters&sort&page` | rows | 7 d |
| `GET /refdomains?t&page` | rows | 7 d |
| `GET /anchors?t&page` | rows | 7 d |
| `GET /history?t` | — | 7 d |
| `GET /compare?t1&t2[&t3]` | 1 report | 7 d |
| `GET /list/export.csv` | 1 export | — |

## 5. Frontend
- [ ] **Backlinks Overview**: KPI cards, history chart (backlinks + ref domains), new/lost bars, follow/nofollow donut, top anchors, top ref domains
- [ ] **Backlinks** table: filters (follow, new/lost, anchor contains, source authority), export
- [ ] **Referring Domains** and **Anchors** tables
- [ ] **Compare** view for up to 3 targets

## Tests
- Rank rescale function, scope handling (domain vs URL)
- Pagination cost: page 2 fetched only when requested
- Fixture-based snapshot tests for all normalizers

## Exit criteria
- [ ] Overview + tables render for a large and a small domain (IN + US)
- [ ] Cost per backlink report known and within budget plan
- [ ] Exports limited by plan

## Risks
| Risk | Mitigation |
|---|---|
| Backlinks API is the priciest family | Strict row caps per plan; 7-day cache; no auto-refresh |
| Large sites → millions of links | Only provider-side paging; never full pulls on free plan |

## Your actions
- [ ] Confirm Backlinks API enabled; note per-row/per-request price for plan design
