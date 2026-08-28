# /for-sale-v3 Members Soft-Gate — A/B test build

**What:** Replace the failing `/exclusive-access` wall (0 leads ever) with a value-first
delayed gate on the real feed. The "Houses for sale" Traffic ad lands people straight on
`/for-sale-v3`, they answer the ladder and scroll, and **20s after the ladder is
dismissed** the feed blurs and a **members gate** appears offering **Facebook (primary),
Google, and email**. Built 2026-08-29.

**Scope:** This ad only. The gate arms **exclusively** when the visitor arrives with
`?gate=1` (the destination we set on the ad) and hasn't already signed up. Organic / every
other campaign never sees it — the feed stays open and crawlable.

**Recognition bonus:** a successful sign-in writes the shared `fields_lead_signup`
localStorage key — the same key `/property`'s PropertyGate reads — so unlocking here ALSO
unlocks the property pages on that device. This is the subscriber-unlock mechanism from
[[README]] delivered as a side effect.

---

## Code (built, compiles, NOT yet deployed)

| File | Change |
|---|---|
| `src/components/DecisionFeedV3/ForSaleGate.tsx` | **New.** The gate overlay — FB + Google + email, blur+lock, analytics. |
| `src/components/DecisionFeedV3/ForSaleGate.module.css` | **New.** Styles (light + dark). |
| `src/pages/DecisionFeedV3Page/DecisionFeedV3Page.tsx` | Eligibility (`?gate=1`), 20s-after-ladder timer, render. |
| `netlify/functions/lead-signup.mjs` | Accept `method: "facebook"` — verifies the FB token server-side via Graph `/me`, pulls name+email from Facebook, asks for email only if FB returns none. |

- Verified: `tsc --noEmit` 0 errors; `npm run build` passes.
- Kill switch: PostHog flag **`forsale_softgate_v1 = false`** disables it with no redeploy.
- No Netlify env change needed — the backend verifies with the user token alone (no app
  secret required for `/me`).

---

## Facebook Login — Meta dashboard setup (Will's action)

App: **Fields Real Estate Content** — App ID `891087910515484`
(developers.facebook.com/apps/891087910515484). Privacy Policy URL already set ✓.

1. **Add the "Facebook Login" product** → Web.
2. **Facebook Login → Settings:**
   - Client OAuth Login: **On**
   - Web OAuth Login: **On**
   - Login with the JavaScript SDK: **On**
   - **Allowed Domains for the JavaScript SDK:** `fieldsestate.com.au`
   - Valid OAuth Redirect URIs: `https://fieldsestate.com.au/`
   - Enforce HTTPS: On
3. **App Settings → Basic:**
   - **App Domains:** add `fieldsestate.com.au`
   - Add Platform → **Website** → Site URL `https://fieldsestate.com.au`
   - **Data Deletion Instructions URL:** `https://fieldsestate.com.au/privacy` (Meta
     requires a data-deletion URL for Login apps)
4. **Switch the app to Live mode** (top toggle). Required for public users to log in — in
   Development mode only app admins/testers can.
5. **Request Advanced Access for the `email` permission** (App Review → Permissions, or
   Use Cases → Authentication → Customize). `public_profile` (name + FB id) is standard and
   needs no review — so one-tap works immediately; `email` may need a short review
   submission. Business verification is likely already satisfied (we run ads).
   - **The build degrades gracefully if `email` isn't live yet:** a Facebook user with no
     email returned is simply asked to type one (the `need_email` path). So we can launch
     before the `email` review clears.

**To test before going Live:** add yourself as a Tester under App Roles, then the FB button
works for your account in Development mode.

---

## Ad repoint (do together, after Meta config)

Change the Traffic ad's destination:
- **From:** `https://fieldsestate.com.au/exclusive-access`
- **To:** `https://fieldsestate.com.au/for-sale-v3?gate=1`

Ad: `Subscriber Lookalike — Houses for sale (Advantage+) Ad` (`120252450388660134`).
This is the A/B: gate-on `/for-sale-v3?gate=1` vs the old `/exclusive-access` wall.
Log to `system_monitor.ad_decisions`.

---

## How we read the result

- **PostHog events:** `v3_softgate_shown` → `v3_softgate_method_click` (method) →
  `v3_softgate_unlocked` (method). Funnel = shown → unlocked, split by method.
- **Leads:** `system_monitor.lead_signups` where `source = "for_sale_v3_softgate"`,
  `method` ∈ facebook / google / form. Compare capture rate vs the `/exclusive-access`
  `subscribers` (source `fb_ad_v4b_lp`) baseline of 0.

---

## Deploy sequence (pending)

1. Will completes the Meta config above.
2. Deploy the 4 files → visual-verify (Rule 4): screenshot normal `/for-sale-v3` (must be
   unchanged) + `/for-sale-v3?gate=1` after the 20s trigger (gate shown); read PNGs; check
   console + network.
3. Repoint the ad, log the ad decision.
4. Watch the funnel; iterate copy/timing.
