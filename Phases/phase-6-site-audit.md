# Phase 6 — Site Audit

**Weeks:** 10–11 · **Online server:** required (crawls run on the VM)

## Goal
Own crawler (Scrapy) that audits a project's site: ~40 issue rules, health score, issue explorer, scheduled re-crawls, run-to-run diff.

## Prerequisites
- Phase 4 stack running; VM has CPU/RAM headroom
- Project domain ownership verified (prevents crawling others' sites at depth)

## Scope
**In:** HTML crawl, optional JS rendering, robots.txt + sitemap, 40 rules, health score, run diff, weekly schedule, Core Web Vitals via PageSpeed API (sampled).
**Out:** log-file analysis, custom extraction, crawling non-verified domains beyond 100 pages.

## 1. Domain verification
- [ ] Methods: DNS TXT record **or** HTML meta tag **or** connected GSC property (Phase 4)
- [ ] Unverified → max 100 pages

## 2. Crawler (`packages/crawler`, Scrapy)
- [ ] Runs as **subprocess** from Celery task (`scrapy crawl audit -a run_id=…`); Twisted reactor can't restart inside a worker
- [ ] Settings: obey robots.txt, `AUTOTHROTTLE`, per-host concurrency 2, identifiable UA `SeoMasterBot/1.0 (+https://<domain>/bot)`, timeout 20 s, max pages from plan, depth limit
- [ ] Seeds: start URL + sitemap(s) from robots.txt
- [ ] Per page extract: status, redirect chain, final URL, content type, size, load time, title, meta description, H1s, canonical, robots meta / `X-Robots-Tag`, hreflang, internal/external links, images (src, alt, size), word count, structured data present, mixed content
- [ ] `scrapy-playwright` only if "Render JavaScript" enabled (1 concurrent page, memory guard)
- [ ] Stream rows to ClickHouse in batches; update `audit_runs.pages_crawled` every N pages
- [ ] Cancel support (task revoke → kill subprocess)

## 3. Rules engine
- [ ] Rule = pure function over page row (+ site graph for link rules) → `Issue(code, severity, url, details)`
- [ ] Severity: `error | warning | notice`
- [ ] MVP rules (~40):

| Group | Rules |
|---|---|
| Status | 4xx, 5xx, redirect chains (>1 hop), redirect loops, 3xx in internal links |
| Titles/meta | missing, duplicate, too long/short title & description |
| Headings | missing H1, multiple H1, duplicate H1 = title |
| Indexing | noindex pages, canonical to non-200, canonical mismatch, blocked by robots but in sitemap, non-indexable in sitemap |
| Links | broken internal, broken external, orphan pages (in sitemap, no inlinks), too many on-page links, nofollow internal |
| Content | thin content (< 200 words), duplicate content (simhash), low text/HTML ratio |
| Images | missing alt, broken images, large images (> 200 KB) |
| International | hreflang errors (missing return link, invalid codes) |
| Security | HTTP pages, mixed content, missing HSTS |
| Performance | slow response (> 1 s TTFB), large HTML, CWV poor (PageSpeed sample) |
| Files | robots.txt missing/invalid, sitemap missing/invalid/4xx |

- [ ] **Health score** = 100 × pages without errors / pages crawled, warnings weighted 0.25 (document formula in UI)

## 4. Data
Postgres: `audit_campaigns`, `audit_runs` (status `queued|running|done|failed|cancelled`)
ClickHouse: `audit_pages`, `audit_issues`, `audit_links(run_id, from_url, to_url, anchor, nofollow)`

## 5. Jobs (`audit` queue, concurrency 1–2)
| Task | Trigger |
|---|---|
| `audit.run` | user "Run" or Beat weekly schedule |
| `audit.score` | after crawl: rules → issues → health score |
| `audit.diff` | compare with previous run: new/fixed issues |
| `audit.cwv_sample` | PageSpeed API on top N pages |

## 6. API (`/api/v1/audit`)
| Endpoint | Quota |
|---|---|
| `POST/GET/PATCH /campaigns` | `audit_campaigns` |
| `POST /campaigns/{id}/run`, `POST /runs/{id}/cancel` | `audit_pages` per month |
| `GET /runs/{id}` (progress) | — |
| `GET /runs/{id}/issues?severity&code` | — |
| `GET /runs/{id}/pages?filters` | — |
| `GET /runs/{id}/diff` | — |
| `GET /runs/{id}/export.csv` | exports |

## 7. Frontend
- [ ] Setup wizard: start URL, page limit, JS rendering toggle, schedule, verification step
- [ ] Live progress (poll `GET /runs/{id}` every 3 s)
- [ ] Overview: health score gauge + trend, errors/warnings/notices, top issues, crawled pages by status
- [ ] Issue explorer: per issue → affected URLs, "why it matters" + "how to fix" text
- [ ] Pages table with filters; diff view (new/fixed)

## Tests
- Each rule: positive + negative fixture HTML
- Crawler against local fixture site (docker nginx with known issues) → expected issue set
- robots.txt obeyed; page cap respected; cancel works

## Exit criteria
- [ ] 1,000-page site audited in < 10 min on the VM
- [ ] Fixture site → 100% expected issues found, 0 false positives on clean pages
- [ ] Weekly scheduled audit runs unattended; diff shows fixed issues

## Risks
| Risk | Mitigation |
|---|---|
| Crawling abuse / complaints | Verification gate, robots.txt, UA with contact URL, per-host throttle |
| VM memory with JS rendering | Off by default; 1 browser page at a time |
| Long crawls block queue | Separate `audit` queue + concurrency cap |

## Your actions
- [ ] Publish `/bot` page explaining the crawler
- [ ] Google PageSpeed API key (free) if CWV wanted
