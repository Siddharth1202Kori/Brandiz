# SeoMaster — Delivery Phases

Detailed plan per phase. Source of truth for architecture: [`docs/03-seomaster-blueprint.md`](../docs/03-seomaster-blueprint.md).

| # | Phase | Weeks | File | Needs online server? |
|---|---|---|---|---|
| 0 | Foundation | 1–2 | [phase-0-foundation.md](phase-0-foundation.md) | No (local docker) |
| 1 | Keywords | 3–4 | [phase-1-keywords.md](phase-1-keywords.md) | No |
| 2 | Domains | 5 | [phase-2-domains.md](phase-2-domains.md) | No |
| 3 | Backlinks | 6 | [phase-3-backlinks.md](phase-3-backlinks.md) | No |
| 4 | Google Search Console | 7 | [phase-4-gsc.md](phase-4-gsc.md) | **Yes** (daily sync) |
| 5 | Rank Tracking | 8–9 | [phase-5-rank-tracking.md](phase-5-rank-tracking.md) | Yes |
| 6 | Site Audit | 10–11 | [phase-6-site-audit.md](phase-6-site-audit.md) | Yes |
| 7 | Billing & Launch | 12–13 | [phase-7-billing-launch.md](phase-7-billing-launch.md) | Yes |

## Locked stack (doc 03 §12)
Python 3.12 · FastAPI · Celery + Beat · Scrapy · Postgres (Neon) · ClickHouse · Redis (Upstash cache, VM broker) · React + Vite + `@semcore/*` · Markets IN + US · Free-tier hosting.

## Rules every phase follows
1. **Every provider call goes through the DAL** (cache → single-flight → provider → normalize → store → meter). No adapter is called from a router directly.
2. **Every report view is metered** against plan limits (`usage_counters`).
3. **Every provider call is logged** to `provider_calls` with its cost.
4. **Tests first** for normalizers, limits and rules engines; recorded provider fixtures (no live calls in CI).
5. **No secrets in repo.** `.env` is git-ignored before the first commit.
6. **Phase is done only when its exit criteria pass**, not when code is written.

## Phase file template
Each phase file has: Goal · Prerequisites · Scope (in/out) · Backend · Data · Providers & cost · Frontend · Jobs · Tests · Deliverables · Exit criteria · Risks · Your actions.

## Status
| Phase | Status | Started | Done |
|---|---|---|---|
| 0 | code complete — awaiting your Google-login check + first push to GitHub (CI) | 2026-10-29 | |
| 1 | code complete — awaiting DataForSEO account verification + live speed check | 2026-10-30 | |
| 2 | not started | | |
| 3 | not started | | |
| 4 | not started | | |
| 5 | not started | | |
| 6 | not started | | |
| 7 | not started | | |
