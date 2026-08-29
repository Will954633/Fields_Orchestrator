# Easthill Valuation Reel Ad — LEADPAGE

_Auto-generated 2026-08-29 from the Meta Ads API. Edit freely — notes below are yours._

| | |
|---|---|
| **Ad ID** | `120252455020290134` |
| **Status** | ACTIVE |
| **Created** | 2026-08-28T20:40 |

## Campaign
- **Name:** Easthill Valuation Reel — LEADS (What the comps say, Aug 2026)
- **ID:** `120252441135610134`
- **Objective:** OUTCOME_LEADS

## Ad set
- **Name:** Easthill Valuation LEADPAGE · Robina+Varsity+Burleigh (pixel Lead)
- **ID:** `120252455019900134`
- **Daily budget:** $15.00/day
- **Optimization:** OFFSITE_CONVERSIONS
- **Targeting:** Varsity Lakes, Robina, Burleigh Waters · age 25-65

## Creative / destination
- **Type:** VIDEO
- **Destination:** in-form / native creative
- **CTA:** —

## History & intent

**Why we created it**
- Outcome-first valuation reel (verified Easthill sale at +$76,000 above guide — 159 Easthill Dr sold $1,425,000 vs $1,349,000 guide — plus real comps and 230-Robina-sales proof) to convert owners wanting a valuation better than a generic single-card CTA (2026-08-27).
- Original creative promised "no email, no sales call", so it deliberately sent traffic to the address-only `/analyse-your-home` page rather than a lead form.

**What changed (pivots)**
- **Traffic → instant lead form:** The reel was mistakenly built as OUTCOME_TRAFFIC/LINK_CLICKS, so it optimised for cheapest clicks with a Learn More link and captured no contact. Rebuilt 2026-08-27 as OUTCOME_LEADS with an on-ad instant form (prefilled name+phone, custom property-address question). Meta can't change objective/optimisation in place, so a new campaign was required.
- **Instant form → website LEAD capture (current LEADPAGE):** On 2026-08-28 (Will's direction) the funnel was converted to keep the low-friction address-first entry but land on `/what-the-comps-say`, which now runs address → name+phone capture ("where should we send your comps?"). The pixel **Lead** fires on the name+phone capture step, not the address. Built as a WEBSITE + OFFSITE_CONVERSIONS(LEAD) ad set under the existing OUTCOME_LEADS campaign at $15/day; the OUTCOME_TRAFFIC arm was paused to avoid double-spend, and the old on-ad instant-form ad set stays paused.

**What we're looking for now**
- Callable seller leads: completed name+phone captures, i.e. `offsite_conversion.fb_pixel_lead` in the campaign insights `actions` — the event the ad set optimises on (it was 0 while capture was broken).

## Notes / hypothesis / performance
_(add observations, what this ad is testing, results)_
