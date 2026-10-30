# Phase 7 — Billing & Launch

**Weeks:** 12–13 · **Online server:** required

## Goal
Take money in both markets (Stripe for US, Razorpay for India), map plans to entitlements, polish onboarding and reports, launch publicly.

## Prerequisites
- Phases 0–6 done and stable
- Business details for payment accounts (KYC), tax registration as applicable
- Costs per report known from `provider_calls` → plan pricing set

## Scope
**In:** plans/pricing page, checkout, subscriptions, webhooks → entitlements, customer portal, invoices, upsell surfaces, onboarding, PDF/CSV reports, legal pages, launch checklist.
**Out:** usage-based overage billing, white-label, public API (later).

## 1. Pricing design
- [ ] Per plan: price (INR for IN, USD for US), limits_json values
- [ ] Margin check: (worst-case provider cost per user/month from ledger) ≤ 30% of plan price
- [ ] Annual discount; free plan limits final

## 2. Payments
| Market | Provider | Objects |
|---|---|---|
| US / international | Stripe | Products/Prices, Checkout Session (subscription), Customer Portal, webhooks |
| India | Razorpay | Plans, Subscriptions, Checkout, webhooks; GST invoice fields |
- [ ] Market chosen by user's billing country (not IP)
- [ ] `billing_provider` + `billing_customer_id` on `orgs`

## 3. Webhooks → entitlements (`/api/v1/billing/webhooks/{stripe|razorpay}`)
- [ ] Verify signatures (`STRIPE_WEBHOOK_SECRET`, `RAZORPAY_WEBHOOK_SECRET`)
- [ ] Idempotency: store processed event ids
- [ ] Events: subscription created/activated/updated/cancelled, payment failed → `orgs.plan_id` + `subscription_status`
- [ ] Grace period on failed payment (e.g. 7 days) → then downgrade to free (data kept, limits drop)
- [ ] Downgrade handling: over-limit rank keywords paused, not deleted

## 4. Product polish
- [ ] Upsell surfaces: `meta.limited` banners, limit-reached modal with plan compare
- [ ] Onboarding: create project → connect GSC → add 10 rank keywords → run audit (checklist on dashboard)
- [ ] Reports: PDF export (WeasyPrint) for Domain Overview, Rank, Audit; scheduled email report (pro+)
- [ ] Transactional email live (Resend/Brevo): verify, reset, receipts, alerts, weekly digest
- [ ] Empty states, error states, loading skeletons everywhere

## 5. Legal & trust
- [ ] Terms of Service, Privacy Policy (GSC data use, retention, deletion), Cookie notice, Refund policy
- [ ] Data deletion: account delete → purge Postgres + ClickHouse rows + revoke GSC token
- [ ] Provider terms re-checked (caching/resale of DataForSEO + SERP data)

## 6. Launch readiness
- [ ] Load test key endpoints (cached) — Render free/paid limits known
- [ ] Sentry alerts, uptime monitor (free, e.g. UptimeRobot) on `/healthz`
- [ ] Backups verified by **restore** test (R2 → fresh ClickHouse; Neon point-in-time)
- [ ] Budget guard caps set for launch traffic
- [ ] Security pass: dependency audit, OWASP checks on auth/webhooks, secrets only in platform envs
- [ ] Decide upgrades from doc 03 §15.4 (Render always-on first)

## Tests
- Webhook signature + idempotency (replay same event → one change)
- Plan change → limits change immediately
- Full paid signup E2E in test mode for both Stripe and Razorpay (Playwright)

## Exit criteria
- [ ] Real paid signup works end to end in **both** IN (Razorpay) and US (Stripe)
- [ ] Cancel/downgrade/failed payment paths verified
- [ ] Legal pages live; data deletion works
- [ ] Restore test passed

## Risks
| Risk | Mitigation |
|---|---|
| KYC/approval delays for payment accounts | Apply at start of Phase 6 |
| Cold starts at launch | Upgrade Render to always-on before announcing |
| Provider cost spike from launch traffic | Budget guard + vendor spend alerts |

## Your actions
- [ ] Apply for Stripe and Razorpay accounts (KYC) early
- [ ] Final prices per plan in INR and USD
- [ ] Legal pages review
