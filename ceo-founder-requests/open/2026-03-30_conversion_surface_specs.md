# 2026-03-30 Conversion Surface Specs

## Status: BACKEND READY — Awaiting Will's approval for website implementation

## 1. Property Page Utility Capture

### Goal

Use the property page as a single-purpose capture surface for low-traffic buyer intent.

### Primary CTA

Headline: `Track price changes for this property`

Support copy: `Get an email if the asking price changes or the listing status updates.`

Field label: `Email`

Button: `Track this property`

Confirmation: `You're on the list. We'll email you if this property changes.`

### Placement

- Above the fold, directly under the hero facts and current asking status.
- One field and one button only.
- Do not place `Analyse Your Home` or Decision Feed signup above the fold on the same page.

### Measurement Plan

- `price_alert_impression`
- `price_alert_submit_start`
- `price_alert_submit_success`
- `price_alert_return_visit_after_signup`

Event properties:

- `property_id`
- `suburb`
- `source_page`
- `source_channel`
- `listing_status`
- `price_displayed`

### Product Rule

For Sprint 1, this page answers one question only: "Do users want help monitoring this property?" If yes, expand later. If no, do not add more CTA clutter and call it experimentation.

## 2. Seller Sale-Reality Checker

### Working Title

`What will I actually keep if I sell?`

### User Problem

Seller search intent is dominated by capital gains tax and net-proceeds uncertainty, but Fields currently packages most proof around listing stories and buyer evaluation.

### First Version Scope

Inputs:

- Property address
- Estimated ownership type
- Broad hold period band
- Purchase price or estimate
- Planned sale timing band

Outputs:

- Estimated sale range
- Likely agent and marketing cost range
- Simple net proceeds range
- Capital-gains-tax guidance guardrail copy
- CTA: `Request a custom sale reality review`

### Guardrails

- No personalised tax advice language
- Use ranges, not definitive tax liabilities
- Add disclaimer that final tax position depends on the seller's circumstances and accountant advice

### Recommended CTA Copy

Headline: `Before you sell, know what you might actually keep`

Body: `See a realistic sale range, common selling costs, and the tax questions to check before you list.`

Button: `Check my sale reality`

### Measurement Plan

- `sale_reality_impression`
- `sale_reality_start`
- `sale_reality_complete`
- `sale_reality_request_review`

---

## Backend Implementation (Completed)

### MongoDB Collections Created

| Collection | Database | Purpose |
|-----------|----------|---------|
| `price_alert_subscriptions` | system_monitor | Email + property tracking subscriptions |
| `price_alert_notifications` | system_monitor | Notification queue and delivery log |
| `sale_reality_submissions` | system_monitor | "Request a review" form submissions |

### Indexes

- `price_alert_subscriptions`: unique(email, property_id), status, property_id
- `price_alert_notifications`: created_at, (subscription_id, created_at), sent
- `sale_reality_submissions`: created_at, email, status

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/process_price_alerts.py` | Subscribe/unsubscribe, match price events to watchers, send notifications (Telegram now, email later) |
| `scripts/sale_reality_calculator.py` | Estimate net proceeds from selling — agent costs, marketing, conveyancing, CGT guidance, all in ranges |

### What Still Needs Will's Approval

1. **Property page CTA component** — React component for the "Track this property" form
2. **Netlify function** — API endpoint to accept subscriptions from the website
3. **Sale Reality page** — New route + React page for the calculator
4. **PostHog events** — Wire up the measurement plan events
5. **Email notifications** — Currently sends via Telegram; needs Gmail API integration for subscriber emails
