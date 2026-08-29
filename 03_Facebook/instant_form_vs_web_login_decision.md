# Facebook lead capture for "Houses for sale" buyer traffic — decision record

**Date:** 2026-08-29
**Owner:** Will
**Status:** Decided — use Meta's **native Instant Form** for Facebook capture; **web
Facebook Login is abandoned** as unworkable in the Facebook in-app browser.

This documents a long debugging session so we never repeat it. Read this before
attempting any "sign in with Facebook on the website" work again.

---

## 1. The goal

The "Houses for sale" ads (buyer-facing, in-app-browser traffic) should capture the
lead with **minimum friction**, ideally one tap, because the person is already logged
into Facebook. Then let them into the `/for-sale` listings.

## 2. What we shipped along the way (all live)

1. **Lead classification fix** (`scripts/fb-lead-puller.py`): the two "Independent
   Listing Analysis (carousel)" forms were mislabelled `SELLER` and announced as "call
   them — seller". They are **buyers**. Moved them (and the four Subscriber buyer-landing
   forms) into a new **`FORSALE_BUYER_FORMS`** set with a `notify_forsale_buyer()` alert
   ("🏠 wants for-sale listings"). See fix-history `[LEAD-BUYER-VS-SELLER-MISLABEL]`.
2. **Ad name in Telegram lead alerts** (`fb-lead-puller.py`): alerts now show the exact
   **ad name** (🏷️), not just the campaign/form name, via `source_lines()`. Fix-history
   `[TELEGRAM-LEAD-NO-AD-NAME]`.
3. **`/for-sale-v3` members soft-gate** — a **value-first, delayed** gate: land on the
   real feed, answer the ladder, browse ~20s, THEN the feed blurs and a members gate
   asks for sign-in. Armed **only** with `?gate=1` (this ad's destination), never for
   organic. Kill switch: PostHog flag `forsale_softgate_v1=false`. Files:
   `src/components/DecisionFeedV3/ForSaleGate.tsx` (+`.module.css`),
   `src/pages/DecisionFeedV3Page/DecisionFeedV3Page.tsx`. It writes the shared
   `fields_lead_signup` localStorage key, so a signup here ALSO unlocks `/property`
   (see `21_User_Journeys/Unlocking_Site_For_Subscribers/`).
   **The gate now offers Google + email only** (Facebook button removed 2026-08-29).

## 3. Why the `/exclusive-access` wall failed (the thing this replaces)

The "Advantage+ Houses for sale" **Traffic** ad pointed at `/exclusive-access`, an
**upfront typed name+email wall**. Result: **0 subscribers, ever** (source
`fb_ad_v4b_lp`; total site subscribers = 4, all from the footer). The endpoint works —
people simply won't type into a wall on a cold mobile tap. That is why we went
value-first, and why an **autofilled** capture matters.

## 4. The Facebook web-login rabbit hole — and why we abandoned it

We tried to add "Continue with Facebook" to the on-site gate. It does **not** work in
the **Facebook iOS in-app browser (WKWebView)** — the exact environment all this traffic
lives in. The full chain of failure:

1. **JS SDK `FB.login()` popup** — the in-app WKWebView suppresses popups. Fails with
   Facebook's generic *"Sorry, something went wrong."* (Worked in normal Safari/Chrome,
   failed in the FB app — proving it's WebView-specific.)
2. A **paid consultant** confirmed the diagnosis and two things we'd missed:
   - **Graph API v18.0 is EXPIRED** (EOL 2026-01-26; current is v26.0).
   - The SDK's in-app fallback uses the **live landing URL** as `redirect_uri`, which
     carries **`fbclid`/`utm`** — so it can never satisfy Meta's exact-match redirect
     rule under Strict Mode.
3. We **rebuilt it the correct way**: a **server-side authorization-code flow** on
   **v26.0** with **one fixed callback URI** (`/auth/facebook/callback`), no SDK, no
   popup. Endpoints: `netlify/functions/facebook-login.mjs` +
   `facebook-callback.mjs`. **Still failed** — "something went wrong" now at Facebook's
   **consent step**, in BOTH the FB browser and normal Chrome.
4. Root blocker: Facebook requires a **saved, validated Privacy Policy URL** before it
   will show a consent dialog that requests `email` — and the new login app's Basic
   settings **would not save the Privacy Policy URL** (reverts to blank). The page IS
   reachable (our geo-block no longer blocks anyone since 2026-08-18; `/privacy` returns
   200 to every UA/IP), so it's Facebook's own form/validation, not us. Setting it via
   Graph API is **disabled** for the app (`error #10`).
5. **The insight that ended it** (Will): a page inside Facebook's app is *still a website
   in a WKWebView* — it does **not** inherit the native app's Facebook session. There is
   **no documented web API** that says "use the account logged into this host app." So
   web Facebook Login can never guarantee the passwordless one-tap we wanted anyway. The
   consultant said the same: keep a non-Facebook fallback; you cannot promise one-tap.

**Conclusion: web Facebook Login was swimming upstream.** The native mechanism that
delivers exactly what we wanted — the already-authenticated Facebook identity, autofilled
— is the **Instant Form**.

## 5. The decision: use Meta's native Instant Form

The Instant Form opens **inside the Facebook app**, **autofilled** with name/email/phone
from the profile. It sidesteps EVERYTHING above: no OAuth, no popup, no WebView redirect,
no privacy-policy validation, **no App Review for `email`** (that hurdle is web-login
only). And we're already built for it — `fb-lead-puller.py` ingests Instant Form leads,
notifies, and CRM-syncs.

**The Instant Form ad already exists and is ACTIVE:**
- Ad: **Subscriber Lookalike LEADFORM — Houses for sale** (`120252455742200134`)
- Form: `1017406421335871` — *"Subscriber access — Advantage+ leadform
  (name+email+phone)"* — asks **FULL_NAME + EMAIL + PHONE** (all autofilled), thank-you
  "Continue" → `/for-sale-v4b`.
- It has barely spent ($1.53 / 29 impressions) — it is **unfunded**, not broken.

### The two arms (the A/B)
- **Arm A — Instant Form (Facebook path):** fund the LEADFORM ad. Autofilled in-app
  capture → thank-you → `/for-sale` listings.
- **Arm B — on-site soft-gate:** the value-first `/for-sale-v3?gate=1` gate, capturing
  via **Google + email**.

Measure which captures more, and at what quality.

## 6. Current state (what's live vs dormant)

| Thing | State |
|---|---|
| `/for-sale-v3` soft-gate, Google + email | **Live**, armed only on `?gate=1` |
| Facebook button on the gate | **Removed** 2026-08-29 |
| `/auth/facebook/start` + `/auth/facebook/callback` endpoints | **Deployed but DORMANT** — nothing links to them; kept for a possible future revisit |
| `?fbauth=` return handling in DecisionFeedV3Page | Retained (harmless; only fires if the dormant endpoints are used) |
| Netlify env `FACEBOOK_LOGIN_APP_SECRET` | **Set** (encrypted; for the dormant flow) |
| FB login app `2222673141908476` ("Fields Estate — Website Login") | Created, **Development mode**, privacy policy won't save, app icon missing — **not usable for public web login** |
| LEADFORM Instant Form ad `120252455742200134` | **Active, unfunded** |
| Traffic ad → `/exclusive-access` (`120252450388660134`) | Active, converts 0% — **candidate to pause/repoint** |

## 7. ⚠ What to watch for

1. **Do NOT retry web Facebook Login in the FB in-app browser** expecting one-tap. It is
   not reliable there and cannot inherit the native session. If ever revisited, use the
   **server-side code flow** (already built, dormant), on the **current** Graph version,
   with a **fixed callback URI** (never the landing page), and know you STILL need: app
   Published, Privacy Policy saved, and `email` via App Review. The dormant endpoints
   hardcode `v26.0` and app id `2222673141908476` — **bump the version** if revisited
   later (Meta expires versions ~2 years).
2. **Graph API version:** anything touching FB must be on a **supported** version. v18.0
   expired 2026-01-26. `fb-lead-puller.py` and older scripts still call `v18.0` — they
   work for now but are on borrowed time; migrate on the next touch.
3. **Instant Form email needs no App Review** (native), but **web-login email does**
   (Advanced Access). Don't conflate them.
4. **Recognition gap:** an Instant Form lead lands on `/for-sale-v4b` (or `/property`)
   **anonymous** — the thank-you URL can't carry a per-lead token, so the site can't
   auto-recognise them. This is the same gap documented in
   `21_User_Journeys/Unlocking_Site_For_Subscribers/`. If we want them unlocked on
   arrival, suppress the gate for lead-form traffic (a thank-you URL param) rather than
   trying to identify them.
5. **The soft-gate is behind `?gate=1`.** Organic `/for-sale-v3` is never gated (and must
   stay crawlable). Any ad meant to hit the gate must use `/for-sale-v3?gate=1`.
6. **Kill switch:** PostHog flag `forsale_softgate_v1=false` disables the gate with no
   redeploy.
7. **The login app's Privacy Policy won't save via UI and API changes are disabled** — if
   we ever need that app live, this must be solved first (likely needs the app icon +
   category + all required Basic fields present so Facebook's all-or-nothing form saves).

## 8. Decisions still pending (Will)

- [ ] **Fund Arm A** (the LEADFORM Instant Form ad) — an ad-budget change; log to
      `system_monitor.ad_decisions`.
- [ ] **Pause or repoint the `/exclusive-access` Traffic ad** (0% conversion). If keeping
      an on-site arm, repoint to `/for-sale-v3?gate=1`.
- [ ] Decide whether to run A vs B head-to-head or just switch to the Instant Form.

## 9. Related records

- `21_User_Journeys/Unlocking_Site_For_Subscribers/README.md` — subscriber recognition /
  site-unlock concept (the `fields_lead_signup` mechanism this gate feeds).
- `21_User_Journeys/Unlocking_Site_For_Subscribers/for_sale_v3_softgate_AB.md` — the
  soft-gate build (note: its "Facebook primary" section is superseded by THIS decision).
- fix-history 2026-08-29: `[LEAD-BUYER-VS-SELLER-MISLABEL]`, `[TELEGRAM-LEAD-NO-AD-NAME]`.
