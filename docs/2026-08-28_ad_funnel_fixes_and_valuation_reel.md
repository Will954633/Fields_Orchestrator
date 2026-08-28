# Ad funnel integrity fixes + Valuation Reel conversion switchover
**Date:** 2026-08-28 · **Owner:** Will · **Trigger:** a paid Owner-Market leadpage arrival was shown the whale mid-signup, and the conversion wasn't logging in Meta.

---

## TL;DR
A single reported symptom (whale shown to a paid `/find` arrival) exposed a chain of funnel-integrity bugs across **every website lead ad**. All are fixed. Separately, the **Easthill Valuation Reel** was restructured so Meta optimises for a completed **name+phone capture** instead of raw link clicks.

---

## Part 1 — What was broken, and what I changed

### 1. Whale overlay firing on paid capture landing pages
- **What:** The seasonal whale overlay fired on `/find/*` (and, on audit, `/your-home-evidence`, `/price-your-home`, `/what-the-comps-say`) — all paid landing pages whose only job is to capture a lead. It interrupted signups mid-flow. Confirmed for the reported user on `/find/varsity-lakes` and a second paid arrival on `/find/burleigh-waters`.
- **Why it happened:** `whaleAllowed()` defaults to "show it"; new paid surfaces inherit the whale unless explicitly excluded. Same class as the 2026-08-20 `/your-home` mailer regression.
- **Fix:** Added all four paths to the `whaleAllowed()` deny-list (`src/root.tsx`).

### 2. `/api/campaign-lead` returned 404 → every name+phone silently dropped
- **What:** The `/find` and `/your-home-evidence` pages POST name+phone to `/api/campaign-lead`. That path had **no route** on the live site (404), and the frontend's best-effort `catch {}` swallowed the error. `system_monitor.campaign_leads` was empty — **no lead was ever stored, no Meta Lead fired, no SMS sent.**
- **Why:** `campaign-lead.mjs` was missing the Netlify v2 `export const config = { path: '/api/campaign-lead' }` that its sibling functions use to self-route.
- **Fix:** Added the `config.path` export. Verified end-to-end (POST → 200 → doc written).

### 3. Telegram alerts: uncategorised name+phone forms fired contactless
- **What:** The Instant-Form lead puller's generic `notify()` rendered email/beds/baths but **not name or phone**. Any owner/seller form not hand-listed fired a "New buyer lead" alert with **no way to call them**. Live impact: the Property Narratives campaign ($81.79 spent, 3 leads) sent contactless alerts.
- **Fix:** `notify()` now surfaces Name + 📞 Phone on *any* lead that carries them (universal safety net), and the 4 Narratives forms + the Listing-Analysis copy were categorised as seller (`fb-lead-puller.py`). Recovered 7 already-captured phone numbers and handed them back for follow-up.

### Infrastructure confirmed healthy
- Netlify `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` are set (website alerts fire).
- `fb-lead-puller.py` runs every 3 min, auto-discovers all 30 active lead forms.
- Google Ads: every campaign PAUSED/REMOVED — nothing live.

---

## Part 2 — Valuation Reel: optimise for the contact, not the click

### The decision
Keep the low-friction, **address-first** entry (people will give an address to see a valuation), then ask **name+phone** framed as *"where should we send your results?"* — and have **Meta optimise for that final action**, not for link clicks.

### What changed
**Landing page** `/what-the-comps-say` (`ValuationReelPage`) — kept the ad-matched comps end-card creative (forest/amber, $76,000 hook, Easthill comps table), but replaced "address-only → mini-site" with a four-step flow:
`hook → processing → capture (name + phone) → done`.
The pixel **`Lead` now fires on the name+phone step**, not the address. Name+phone POST to `/api/campaign-lead` (source `fb_valuation_reel`); the SMS poller texts the private link.

**Meta campaign** — you can't change a campaign's objective in place, so I built a new ad set under the existing **`OUTCOME_LEADS`** Easthill campaign and paused the traffic arm:

| Item | Value |
|---|---|
| Ad set `120252455019900134` | ACTIVE — `OFFSITE_CONVERSIONS`, pixel `1491613936314260`, event `LEAD`, WEBSITE, **$15/day** |
| Ad `120252455020290134` | reuses the reel creative → `/what-the-comps-say` |
| Traffic campaign `120252439581970134` | **PAUSED** (was `LINK_CLICKS`) |

---

## Part 3 — What we're looking for in the results

### The one signal that matters first
In Meta Ads Manager (or campaign insights `actions`), watch **`offsite_conversion.fb_pixel_lead`** on the new ad set. It was **0** while capture was broken. Once the ad clears review and delivers, this should climb above 0. **That is the proof the whole funnel works** — click → address → name+phone → pixel Lead received by Meta. The Results column will read **"Leads"** instead of "Link clicks".

### The funnel, stage by stage (where to look)
| Stage | Metric | Where |
|---|---|---|
| Reached the page | `landing_page_view` | Meta insights / PostHog `valuation_reel_page_view` |
| Entered address | PostHog `valuation_reel_address_submit` | PostHog |
| **Completed name+phone** | PostHog `valuation_reel_lead_submitted` + pixel `Lead` | PostHog + Meta |
| Stored lead | `campaign_leads` where `source="fb_valuation_reel"` | DB |
| Alerted | "New buyer enquiry" Telegram | Telegram |
| Texted link | `find_sms`/`reel3_sms_sent` on the lead, `lead_sms_log` | DB |

### What "good" looks like
- **Address-submit rate:** cold FB traffic historically runs ~2% session→submit. A few % of landing-page views reaching the address step is normal.
- **Name+phone completion:** this is the step we've never measured cleanly (it was broken). It's the number to establish a baseline for — what fraction of address-submitters give a phone. This is the whole point of the change.
- **Cost per lead (CPL):** compare across the four website-conversion ads once each has leads — leadpage (`/find`), `/price-your-home`, Reel3 (`/your-home-evidence`), and this one. That tells us which creative/offer converts a paid click into a callable contact most cheaply.

### Expected caveats (not failures)
- **"Learning limited":** at $15/day the ad set won't hit Meta's ~50-conversions/week learning threshold. Expect it to sit in limited learning — that's structural, not a bug. It still optimises on whatever Lead signal it gets.
- **Slow start:** the pixel `Lead` history for this event starts near zero, so early delivery is broad until Meta accumulates examples.
- **7-day-click attribution:** conversions can appear up to a week after the click, so don't judge CPL on day one.

### Red flags to escalate
- **`fb_pixel_lead` stays 0 after real delivery** → capture still isn't firing the pixel (or the whale is back on the page). Check `campaign_leads` count and PostHog `valuation_reel_lead_submitted`.
- **`campaign_leads` grows but no Telegram / no SMS** → downstream wiring broke (the alert or the `*/3` SMS poller).
- **High `address_submit` but near-zero `lead_submitted`** → people bail at the name+phone step; that's a creative/friction signal, not a bug — worth testing the capture copy.

### First concrete check (once the ad is approved and has spend)
1. Meta: does the ad set show any `offsite_conversion.fb_pixel_lead`? Results column reads "Leads"?
2. DB: any `campaign_leads` with `source="fb_valuation_reel"`?
3. Confirm the first real lead produced **both** a "New buyer enquiry" Telegram **and** an SMS.

---

## Records
- Fix-history: `logs/fix-history/2026-08-28.md` — `[WHALE-ON-FIND-LEADPAGE]`, `[FIND-CAMPAIGN-LEAD-404]`, `[WHALE-ON-PAID-LANDINGS]`, `[TELEGRAM-GENERIC-NOTIFY-NO-CONTACT]`, `[VALUATION-REEL-CAPTURE]`
- Ad decision: `system_monitor.ad_decisions` (2026-08-28, new_campaign)
- Commits: website `2cda321`, `be23489`, `995bce9`, `a3fe4d3`, `891e84a`; orchestrator `a33e0a9`, `f26bfb9`
