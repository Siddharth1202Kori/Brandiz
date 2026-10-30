# 01 — Semrush Reverse-Engineering Approach

> Purpose: define *how* we study Semrush with REA so the architecture breakdown (doc 02) and the SeoMaster build are grounded in evidence, not guesses.
> Date: 2026-10-27 · Tooling: REA MCP (web/runtime routes) + isolated Chrome over CDP

---

## 0. Ground rules (read first)

| Rule | Why |
|---|---|
| Observe only what a normal browser receives (HTML, JS bundles, XHR shapes, headers we're sent). | Client-side code shipped to every visitor is fair game for interoperability/competitive study. |
| No auth bypass, no paywall circumvention, no credential reuse, no hitting private APIs outside a logged-in session we legitimately own. | Semrush ToS + computer-misuse law. |
| No bulk scraping of Semrush **data** (keyword DBs, backlink indexes). | Their data is the product and is protected; we study *architecture*, not copy datasets. |
| Low request volume, human-paced. One isolated browser profile. | Avoid rate-limit/abuse triggers and load on their infra. |
| Don't copy proprietary code/assets/branding into SeoMaster. Re-implement from understood behavior. | Clean-room principle. |
| REA keeps payload *shapes* only (values redacted). Keep it that way. | No PII/secret leakage into our docs. |

---

## 1. Initial REA recon (already done)

**Setup:** Chrome 156 launched with `--remote-debugging-port=9222` and a throwaway profile in scratchpad. Target: `https://www.semrush.com/` (public marketing home).

**Evidence:** `ev_6d9784fed9e592aa8896da885ac37f5643e924727c20e021c7ae77933e682fab` (`inspect_web_page`, 4 s window).

### Observations
- **Static asset pipeline:** `/__static__/webpack/<name>.<contenthash>.js` — Webpack, content-hashed, runtime chunk (`runtime.*.js`) + numbered split chunks (`3486`, `5650`, `8808`, `9327`).
- **Named feature entry chunks:** `header`, `footer`, `top_banner`, `global_spinner`, `skip_to_content`, `init_searchbar_api`, `init_folders_api`, `init_component_provider`, `observer_limit_options`, `track_billing_info_usage`, `data_layer_proxy`, `smrwv`.
- **`mf_widgets.*.js`** — name strongly suggests **Webpack Module Federation** (micro-frontends loaded at runtime).
- **`/jsi18n/`** — Django's `JavaScriptCatalog` i18n endpoint → **Django-rendered shell**.
- **`/olaf`** — first-party script endpoint, purpose unknown.
- **Legacy bundle:** `/static/index.<hash>.js` alongside `/__static__/webpack/` → two build generations coexist.
- **Observability/analytics:** `sentry`, `amplitude_session_replay`, `speedcurve_lux` (RUM).
- All 57 recorded resources were first-party `www.semrush.com`; 11 scripts from other origins + 65 URL-less scripts were policy-filtered (not yet attributed).

### Inferences (to verify)
- Hybrid: Django server-rendered shell + mounted React(?) islands/micro-frontends.
- Shared shell services (`init_*_api`) expose globals that tool micro-frontends consume.
- Plan/limit enforcement partly surfaced to client (`observer_limit_options`, `track_billing_info_usage`).

### Gaps from this pass
- Network was **attach-limited**: page loaded before REA attached → no XHR/API calls captured.
- Third-party origins excluded by origin policy → tag stack not inventoried.
- Framework (React? Vue?) not yet confirmed — needs bundle parse.
- Only marketing page seen; the real product lives behind login (`/analytics/...`, `/projects/...`).

---

## 2. Method — phased plan

Each phase = questions → REA tool → evidence → finding ledger entry.

### Phase A — Public surface map (no login)
| Question | REA tool | Output |
|---|---|---|
| Framework, chunk graph, route & API candidates, vendor fingerprints | `analyze_web_bundle` (`detail: summary`, `view: javascript-routes`) | Chunk graph, route list, endpoint candidates |
| What loads on cold navigation (API calls, CDNs, 3rd parties) | `capture_browser_scenario` (launch → navigate, so capture starts *before* load) with wider `allowed_origins` | Full request timeline, JSON *shapes* |
| Which tag/analytics vendors | `inspect_web_page` with explicit third-party `allowed_origins` | Vendor inventory |
| Public free tools (keyword overview / domain overview teasers) | `capture_browser_scenario` with declared actions (type domain → submit) | Public API shapes, rate-limit headers, paywall boundary |
| Source maps leaked? | `analyze_web_bundle` `fetch_source_maps: true` (same origin only) | Original module names if published |

### Phase B — Authenticated app (free account the user owns)
User logs in manually in the isolated browser; REA attaches afterwards (no credentials pass through us).

| Question | REA tool |
|---|---|
| App shell vs tool micro-frontends; how `mf_widgets` resolves remotes | `analyze_web_bundle` + `trace_web_module_imports` |
| Per-tool API contracts: Domain Overview, Keyword Overview, Keyword Magic, Backlinks, Position Tracking, Site Audit, Projects | `capture_browser_scenario` per tool flow, JSON shapes only |
| Realtime/async work (site audit progress, report generation) | `observe_web_session` + websocket shapes |
| Auth/session model (cookie vs token, CSRF, refresh) | header **names** + cookie **names** from capture (values redacted) |
| Plan limits & quota enforcement points | trace `observer_limit_options`, `track_billing_info_usage` via `trace_javascript_semantics` |
| Feature flags / experiments | `trace_javascript_semantics` on bundle globals |

### Phase C — Feature tracing
For each core feature: `trace_application_feature` from a seed (button/route/endpoint) → UI component → state store → API call → response shape → rendering. One ledger row per feature.

### Phase D — Backend inference (black-box, from outside)
Only from what responses reveal:
- API style (REST / GraphQL / RPC), versioning, pagination, error envelopes.
- Response headers → CDN, edge, server tech, cache policy.
- Latency patterns → precomputed DB lookup vs live crawl (e.g. Keyword Overview fast = precomputed; Site Audit slow = job queue).
- Public material (engineering blog, job posts, conference talks) to corroborate — clearly labelled as *external source*, not REA evidence.

### Phase E — Synthesis → doc 02
Produce architecture breakdown: layers, services, data pipelines, per-tool contracts, and a "SeoMaster equivalent" column.

---

## 3. Evidence discipline

Every claim in doc 02 tagged as one of:
- **[OBS]** observed — cites REA Evidence ID.
- **[INF]** inferred — states reasoning + supporting Evidence IDs.
- **[EXT]** external public source — cite URL.
- **[UNK]** unknown — what would resolve it.

Finding ledger kept at `docs/evidence/ledger.md`; full REA bundles exported via `export_evidence_bundle` to `docs/evidence/`.

---

## 4. Deliverables

| # | Doc | Content |
|---|---|---|
| 01 | this file | Method, guardrails, initial recon |
| 02 | `02-semrush-architecture.md` | Frontend, API, backend, data pipelines, per-tool breakdown, unknowns |
| 03 (later) | `03-seomaster-blueprint.md` | What we build, what we buy (SERP/backlink data providers), MVP scope |

---

## 5. Key insight for SeoMaster

Semrush's moat is **data** (crawled backlink graph, clickstream-derived keyword volumes, SERP history), not the UI. Frontend/API architecture we can learn and rebuild; data layer we must source differently (own crawler, SERP APIs, Google Search Console, DataForSEO-type providers). Doc 02 will separate these clearly.

---

## 6. Need from you before Phase B
1. Approve proceeding to doc 02 (Phase A runs automatically).
2. For Phase B: create/own a Semrush free account and log in yourself in the isolated Chrome window REA opens. Skip Phase B if you prefer public-only analysis.
