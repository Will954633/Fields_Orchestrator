# Unlocking the Site for Subscribers

**Goal:** Anyone who signs up (Facebook lead form, on-site gate, AYH report) should get
**full, frictionless access** to the gated content on `/property` — recognised
automatically on return visits, **without being asked to sign in each time**.

**Status:** Concept + implementation plan. Nothing here is built yet. The core
mechanism (below) was designed and **parked on 2026-07-30** (see memory
`parked_lead_token_identity_join`) because it needs a website deploy + frontend change
+ mandatory visual verification.

**Author's framing (Will, 2026-08-29):** the leads coming off the "homes for sale"
buyer ads are *buyers wanting to access our /for-sale listings*. They've given us their
contact details; they should not keep hitting a wall.

---

## 1. The goal, precisely

This is a **friction-removal** problem, not a **security** problem. We are not trying to
stop anyone reading the content (see §5 — the content is already served to everyone).
We are trying to make sure a person who has already given us their details never has to
prove it again.

Success = a signed-up contact lands on any `/property/:id` page and sees everything
unlocked, having done nothing but click a link we sent them once.

---

## 2. How the lock works TODAY

`/property/:id` renders `PropertyPageV2`, whose gated sections are wrapped in
`<GatedBody>` from `src/components/PropertyGate/PropertyGate.tsx`.

**What is gated** (each a `<GatedBody>`):
- Price timeline (rows after the first) — `PropertyTimelineV2.tsx`
- Trade-offs / "what's wrong with it" — `PropertyTradeOffsV2.tsx`
- Costs to buy & hold — `PropertyCostsV2.tsx`
- Legal / land / flood record — `PropertyLegalV2.tsx`

**What is NOT gated:** hero (address, price, beds/baths), valuation range, adjusted
comparables, AI editorial, gallery, floor plans, FAQ, bridge CTA.

**How the lock is enforced — client-side only:**
- `GatedBody` keeps the children in the DOM and applies a **CSS blur** with an unlock
  card overlay. The content is present in the page; the blur is cosmetic.
- The **Netlify function `property.mjs` has no auth check** — it returns the full
  timeline / costs / legal data to any anonymous caller. (Its only filters are
  editorial-quality: unpublished editorial withheld, internal `_`-fields stripped,
  waterfront valuations nulled — none of that is signup-related.)

**What unlocks it:** the single localStorage key **`fields_lead_signup`**.
- Seeded on mount: if the key is present, the whole page unlocks
  (`PropertyGate.tsx:79-89`). Listens for cross-tab `storage` events too.
- Written by two on-site paths, both hitting `/api/lead-signup` first:
  1. The email form in `SignupGate.tsx`.
  2. One-tap "Continue with Google" (GIS) straight from the unlock card.
- `netlify/functions/lead-signup.mjs` only stores the lead + fires notifications. It
  returns **no cookie, no JWT, no session** — persistence is purely the client-written
  localStorage value. Clearing storage re-locks; it is **per-device**.

**There is no logged-in user concept anywhere on the site.** Everything is anonymous +
per-device localStorage, joined to analytics only via the anonymous PostHog
`distinct_id`. Google sign-in is used purely as a lead-capture convenience (the JWT is
decoded client-side, unverified, for name/email — it is not a session token).

### Why this is actually good news
The gate already implements "recognise this device and never ask again." Once
`fields_lead_signup` is set, that browser never sees the gate again — no sign-in. The
**only** missing piece is getting that flag onto a signup's device automatically.

---

## 3. The catch — why Facebook leads are the hard case

A Facebook **Instant Form is filled inside Facebook**. Nothing lands on the person's
browser — no cookie, no token, no session, no distinct_id we can tie to them. So when
they later open a `/property` page, their browser is indistinguishable from a stranger's
and they hit the gate.

Confirmed empirically (Sharon Lansley, 2026-08-28): she submitted the FB form, tapped
the thank-you button to `/for-sale-v3`, and browsed as a **fully anonymous** PostHog
person. No PostHog person carries her email or phone. The thank-you URL Meta stores for
the form is clean (`https://fieldsestate.com.au/for-sale-v3`, no token) and **Meta's
thank-you button cannot carry a unique per-lead token** — so the immediate click-through
cannot self-identify her either.

**Contrast:** someone who signs up *on the site* via the gate is fine — the gate writes
the flag on their own device in that moment. The problem is specifically the
**off-site (Facebook / any form-fill-elsewhere) population.**

The general identity gap, in one line: **we have the contact keyed by email; we have the
browser keyed by anonymous distinct_id; nothing joins the two.**

---

## 4. The solution — a signed "lead token" carried in a link WE send

Because the FB form-fill never touches their browser, the identity token has to arrive
through a channel **we** control: the follow-up **email / SMS** we already send these
leads (we capture both email and phone). That link plants the token; the first click
recognises them; localStorage keeps them recognised thereafter.

### Flow
```
FB lead submitted
      │  (fb-lead-puller.py already ingests + notifies)
      ▼
Welcome email / SMS sent to the lead, containing:
   https://fieldsestate.com.au/for-sale?u=<LEAD_TOKEN>
      │
      ▼  lead clicks the link (on their phone/browser)
Frontend reads ?u=, verifies the token, then:
   • writes localStorage `fields_lead_signup`   ← unlock, same as on-site signup
   • posthog.identify(email)                    ← stitches their whole journey to the contact
   • (optional) drops a durable first-party token for cross-visit server recognition
      │
      ▼
Every later /property visit on that device: unlocked, no sign-in, ever.
```

### The token
Reuse the **existing `?k=` report-link pattern** — a stateless HMAC-SHA256 signature, no
DB round-trip needed:
- Minted from the lead identity (e.g. `HMAC(lead_id|email, SECRET)`), same shape as
  `netlify/functions/db.mjs` report keys (`REPORT_LINK_SECRET`, `src/utils/reportLink.ts`).
- Verifiable server-side (or even trusted client-side for a soft gate) without storing
  per-token state.
- Carries no PII in the URL (opaque signature + a lookup id), so it's safe to email/SMS.

### Why this is ~80% already built
The recognition/verification half already exists from the off-market report system and
can be adapted:
- **Server-issued device token + localStorage + server-verify** — `device_token` minted
  in `analyse-your-home-submit.mjs`, stored at `property_reports.owner.device_token`,
  persisted client-side as `fields_device_token`.
- **Cross-visit / cross-device resolver** — `netlify/functions/my-home.mjs`
  (`GET /api/v1/my-home?distinct_id=&device_token=`) ranks recognition:
  `certain` (device_token match) → `high` (distinct_id match) → CRM address signals.
- **Stateless signed link keys** — `mayReadReport` / `?k=` in `db.mjs`.
- **Email↔browser plumbing already present on-site** — `/api/lead-signup` stores
  `posthog_distinct_id` *next to* email in `system_monitor.lead_signups`. An FB lead has
  the email but no distinct_id; the token-link click is what supplies the missing
  distinct_id binding.

The **missing** half is purely *acquisition*: getting a token into the off-site lead's
browser. That is exactly what the parked lead-token feature was for.

---

## 5. Honest limits (state these to Will before building)

1. **It's per-device.** "Never sign in again" holds on any browser where they've clicked
   our link at least once. A brand-new device or a cleared browser needs one more
   link-click to re-recognise. True cross-device-without-login recognition is not
   achievable without accounts — the link-click model gets ~90% of the value at near-zero
   friction.
2. **The gate is soft.** It's a CSS blur over data the API already serves to everyone. If
   the intent is ever to *actually* restrict access (not just de-friction it for
   subscribers), that is a separate, larger server-side-auth project — flag it, don't
   bundle it.
3. **Verification is mandatory.** Any change here is a website deploy → follow CLAUDE.md
   Rule 4 (deploy tracker + change log + screenshot + read the PNG + console/network
   check). This is part of why the feature was parked.

---

## 6. Implementation checklist

Backend (orchestrator):
- [ ] Token minter: `HMAC(lead_id|email, SECRET)` helper (mirror `reportLink.ts` /
      `db.mjs` key logic; reuse or add a secret).
- [ ] Welcome email/SMS: extend the existing FB-lead follow-up to include the tokenised
      unlock link (`/for-sale?u=<token>`). We already have email + phone per lead in
      `system_monitor.fb_leads`.
- [ ] Decide channel: email, SMS, or both (see §7 — Will's call).

Frontend (website — deploy + visual verify):
- [ ] On `/for-sale` and `/property`, read `?u=` (and/or `?k=`) on load.
- [ ] Verify the token (server endpoint keyed on the signature, or soft client-trust for
      the blur-only gate).
- [ ] On valid token: `localStorage.setItem('fields_lead_signup', …)` and
      `posthog.identify(email)`; strip the param from the URL.
- [ ] (Optional, stronger) mint/store a durable first-party token so recognition can be
      server-verified via a `my-home`-style endpoint, surviving beyond a single device's
      localStorage.

Optional same-session win:
- [ ] Because arrival on `/for-sale-v3` with the buyer campaign UTMs ≈ a completed lead
      submission, we *could* also unlock in that first session directly from the
      thank-you click — before they ever open the email. Lower fidelity (UTM heuristic,
      not identity) but removes the "I just signed up and still hit a wall" moment.

Verification (Rule 4):
- [ ] Deploy tracker log, website change log, screenshot `/property` unlocked-state,
      read the PNG, check console + network-errors.

---

## 7. Open decisions for Will

1. **Channel** for the unlock link — email, SMS, or both?
2. **Same-session unlock** on the thank-you click-through (UTM heuristic), or
   email/SMS-link only?
3. **Scope** — soft de-friction (localStorage + posthog.identify, this doc) now, or also
   build the durable server-verified token for cross-device recognition?

---

## Reference — key files

**Gate (website):**
- `src/components/PropertyGate/PropertyGate.tsx` — provider; `GatedBody` blur;
  localStorage key `fields_lead_signup`
- `src/components/SignupGate/SignupGate.tsx` — on-site email/Google signup
- `netlify/functions/lead-signup.mjs` — stores lead (+`posthog_distinct_id`), no session
- `netlify/functions/property.mjs` — serves full data, no auth gate
- Gated sections: `PropertyTimelineV2.tsx`, `PropertyTradeOffsV2.tsx`,
  `PropertyCostsV2.tsx`, `PropertyLegalV2.tsx`

**Recognition machinery to reuse (website):**
- `netlify/functions/db.mjs` — `mayReadReport`, `?k=` HMAC link keys (`REPORT_LINK_SECRET`)
- `netlify/functions/my-home.mjs` — device_token / distinct_id recognition resolver
- `netlify/functions/analyse-your-home-submit.mjs` — mints `device_token`
- `src/utils/reportLink.ts` — link-key helpers
- `src/pages/YourHomePage/YourHomePage.tsx` — `fields_device_token` localStorage usage

**Lead ingestion + CRM (orchestrator):**
- `scripts/fb-lead-puller.py` — FB lead ingest + Telegram notify (where the welcome
  email/SMS would hook in)
- `scripts/crm_lead_sync.py` — `upsert_lead()`, CRM contact keyed on **email**
- `scripts/crm_sync.py` — PostHog→CRM, keyed on **distinct_id** (the other half of the join)

**Analytics identity:**
- `src/utils/posthog.ts` — `posthog.identify` currently fires for internal users only;
  never for leads (this is the binding we'd add on token-link click)

**Memory:** `parked_lead_token_identity_join`, `report_ownership_device_token`,
`home_recognition_personalization`, `contact_capture_reality_and_address_mail_strategy`,
`crm_attribution_writepath`, `report_link_key_gate`.
