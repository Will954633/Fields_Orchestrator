# Owner Market: switch from website leadpage to autofill Instant Forms
**Date:** 2026-08-28 · **Decided by:** Will · **Executed by:** ops agent

This documents why we moved the Owner Market Facebook campaign off the website
`/find` capture page and onto Facebook native **Instant Forms** (with autofill),
what exactly changed, and what we expect to see in the results.

---

## 1. The evidence that drove this

### Verdict: pure abandonment at a bait-and-switch contact gate — not a capture bug

We investigated why the Owner Market ads were producing **contactless leads**
(address only, no name/phone/email) and **~0 conversions in Meta Ads Manager**.

#### The screenshot evidence (the smoking gun)

**Landing page** (`/find/robina`) makes two promises:

> "Enter your address to **see your home's analysis**." … "Robina, Queensland · **No sign-up.**"

**Capture step** (immediately after they enter the address):

> ✓ ANALYSIS READY — 24 Banff Court, Robina
> **"Where should we send your results to?"**
> [ First name ] [ Mobile number ] → Text me my analysis

The contradiction is the whole problem:

- They were told **"No sign-up"** — this is a sign-up (name + mobile number).
- They were told they'd **"see"** their analysis — it's never shown on-screen; the
  screen says "✓ ANALYSIS READY" then holds it hostage behind a phone number
  ("we'll text you a private link").
- Phone number is the single highest-friction field you can ask a cold Facebook
  visitor for, and it's demanded **before any value is delivered**.

#### The session-replay evidence (5 abandoners, all in one day)

Every one of the 5 contactless Owner Market leads followed an identical
~25–38 second arc:

```
land → search address (3-4 keystrokes) → select address → report_created → LEAVE
```

- **Zero interaction** with the name/phone fields on any of the 5 — no focus, no
  typing, no submit. They see the wall and go.
- Sessions are 23–38s total — they bail 5–15s after the form appears.
- On the two mobile/tablet sessions, a **whale-moment interstitial with
  auto-playing audio** (`whale_shown` + `whale_audio`) fired right at the
  address-submit moment, then `whale_dismissed` + "Close" → leave. So on some
  devices there was an unexpected audio pop-up colliding with the exact
  conversion moment. (This defect was fixed separately the same day —
  see fix-history `[WHALE-ON-FIND-LEADPAGE]`.)

This also definitively **rules out** the "entering details but not captured"
theory: `find_home_lead_submitted` (1) exactly equals stored contacts (1 —
William, captured cleanly with phone). When someone *does* submit, it's stored
perfectly. Nobody is being lost; **5 of 6 simply refuse the gate.**

#### The funnel (PostHog, 7 days)

| Step | Event | Count |
|---|---|---|
| Landed on `/find` | `find_home_page_view` | 102 (101 people) |
| Entered an address | `find_home_address_submit` | 7 |
| ↳ redirected (already listed) | `find_home_currently_listed` | 1 |
| Reached name+phone form | (implied 7 − 1) | 6 |
| **Completed name+phone** | `find_home_lead_submitted` | **1** |

- **Landing → address: 101 → 7 (93% leave)** before entering an address.
- **Address → contact: 6 → 1 (83% abandon)** the name+phone step.

### What it was costing us

The `/find` capture step was one screen doing double damage:

1. **Killed contact capture** — 83% of address-enterers wouldn't give a phone
   number for an unseen result.
2. **Killed Meta optimisation** — the `Lead` pixel was wired to that same
   abandoned step, so Meta saw ~0 conversions and could not optimise the
   `OFFSITE_CONVERSIONS` objective. (This was the original "nothing showing on
   Facebook" question.)

---

## 2. Why Instant Forms fix both at once

| | Website `/find` form | FB Instant Form (autofill) |
|---|---|---|
| Friction | Type name + phone manually, after a "No sign-up" promise | **Name/phone/email autofilled from FB profile** — near-zero |
| Meta attribution | Only if our pixel fires (the thing that broke) | **Native — Meta owns the form, always attributed** |
| Optimisation | Starved (pixel gap) | **Fed** — `LEAD_GENERATION` gets real leads |
| Same-day bugs | Whale interstitial + `/api/campaign-lead` 404 both lived here | **Sidesteps all of it** — no page load, no capture route |
| Address quality | Autocomplete → validated | Free-typed → resolved server-side, human-reviewed if ambiguous |

The decisive fact: the Instant Form ads **already existed** (built, then paused)
and were **already proven** — the day's earliest Owner Market leads (Richard
Vivian, Marjorie Henderson, Mike Wales) came through them and registered natively
with Meta. So this was a switch, not a build.

---

## 3. What we changed

### 3a. Ad delivery (Facebook)
- **Activated** the 3 Instant FORM ads + their ad sets + campaign
  (`Owner Market — Find Your Home (LEAD FORM / SMS link)`, campaign
  `120252423820580134`).
- **Paused** the 3 website LEADPAGE ad sets
  (`Owner Market — Find Your Home (LEAD PAGE / pixel Lead)`).
- Budget unchanged: **$15/day × 3 suburbs = $45/day** (same as the paused ads).

### 3b. New v2 forms (added email)
Meta lead forms are **immutable once they receive leads**, so adding an email
field required **new forms**. Created one per suburb, cloning the proven form and
adding `EMAIL`:

| Suburb | v2 form (live) | Legacy form (retired) |
|---|---|---|
| Burleigh Waters | `1036794049154075` | `2498787700632783` |
| Varsity Lakes | `1541766097148341` | `1574956234128078` |
| Robina | `2855802088118475` | `1664016075454625` |

Fields collected: **home_address, full_name, email, phone_number.**
New creatives were built (form_id swapped in every carousel card) and the 3 FORM
ads repointed to them. Creatives:
Burleigh `1384052266502789`, Varsity `1519881696556699`, Robina `1052111020904960`.

### 3c. Fulfilment (delivers the analysis)
`03_Facebook/Owner_Market_Carousel/owner_market_sms.py` (runs every 3 min via cron):
- `form_map()` now maps **both v2 and legacy** form_ids → suburb.
- Each new lead's address is resolved to its `/your-home` analysis link, then the
  link is delivered by **SMS** (JustCall, when a phone is present) **and email**
  (via `ayh-lead-fulfil`, when an email is present — its own quality gate blocks
  unresolved addresses).
- Self-monitors via `job_run` with a Rule-7b assertion: if leads existed but
  nothing went out on either channel and some failed, it raises.
- Config in `forms_ids.json`. End-to-end tested with a synthetic v2 lead.

### 3d. Notifications
The Telegram lead alert already surfaces name + phone (+ email) for these leads.
Separately, the website AYH lead alert was upgraded today to name the exact source
ad (`[AYH-NOTIFY-AD-NAME]`).

---

## 4. What we're looking to see in the results

**Primary hypothesis:** autofill + native Meta capture converts far more of the
same ad traffic into *contactable* owner leads, and gives Meta real conversions
to optimise on.

Watch over the next 1–2 weeks (same $45/day spend, so this is a like-for-like
comparison against the paused LEADPAGE ads):

1. **Cost per contactable lead falls sharply.** Old path: mostly contactless
   address-only records; effectively very few contactable leads for the spend.
   New path: every lead carries name + phone + email. Target: a real, countable
   cost-per-lead where before it was ~undefined.
2. **Meta Ads Manager "Results" populate.** The FORM ads optimise for
   `LEAD_GENERATION` and leads register natively — Results should show real lead
   counts (subject to the usual minutes-to-hours reporting lag), unlike the
   LEADPAGE ads which showed ~0.
3. **Form open → submit completion rate** should be dramatically higher than the
   website's 6 → 1 (17%) capture rate, because autofill removes the typing.
4. **Fulfilment delivery rate** — % of leads that receive their analysis link by
   SMS and/or email (tracked via `om_sms_sent` / `om_email_sent` on `fb_leads`,
   and the `owner_market_sms` heartbeat on the Systems Health sheet). Watch the
   `unresolved` count (free-typed addresses that don't resolve → human finishes).
5. **Downstream quality** — do these autofilled leads engage with the analysis
   link and convert to conversations, or are they lower-intent than the
   (few) high-friction website completers? This is the main risk of lowering
   friction and is worth watching before scaling budget.

**Known trade-offs being accepted:**
- Free-typed addresses (no autocomplete) → some need human disambiguation; the
  fulfilment quality-gates unresolved addresses rather than emailing a bad link.
- Autofilled email can be stale → some email deliveries may bounce (SMS is the
  backstop; phone is also captured).
- We lose on-page branding / instant on-screen value — acceptable because the
  chosen model is "we'll send your analysis," not "see it now."

**Rollback:** fully reversible — re-activate the 3 LEADPAGE ad sets and pause the
3 FORM ad sets. IDs are in `ad_decisions` (2026-08-28) and `forms_ids.json`.

---

## 5. Object reference

- **FORM campaign:** `120252423820580134`
- **FORM ads:** Burleigh `120252423825770134`, Varsity `120252423823960134`, Robina `120252423822300134`
- **Paused LEADPAGE ad sets:** Burleigh `120252450439110134`, Varsity `120252450438750134`, Robina `120252450437820134`
- **Fulfilment:** `owner_market_sms.py` (cron every 3 min, `--send`), config `forms_ids.json`
- **Logs:** `logs/owner-market-sms.log`; heartbeat `owner_market_sms` on Systems Health sheet
- **Related fixes (same day):** `[WHALE-ON-FIND-LEADPAGE]`, `[FIND-CAMPAIGN-LEAD-404]`, `[AYH-NOTIFY-AD-NAME]`
