# Owner Market FORM Ad · Varsity Lakes

_Auto-generated 2026-08-29 from the Meta Ads API. Edit freely — notes below are yours._

| | |
|---|---|
| **Ad ID** | `120252423823960134` |
| **Status** | ACTIVE |
| **Created** | 2026-08-26T18:49 |

## Campaign
- **Name:** Owner Market — Find Your Home (LEAD FORM / SMS link, Aug 2026)
- **ID:** `120252423820580134`
- **Objective:** OUTCOME_LEADS

## Ad set
- **Name:** Owner Market FORM · Varsity Lakes
- **ID:** `120252423823330134`
- **Daily budget:** $15.00/day
- **Optimization:** LEAD_GENERATION
- **Targeting:** Varsity Lakes · age 25-65

## Creative / destination
- **Type:** SHARE
- **Destination:** `https://fieldsestate.com.au/find/varsity-lakes`
- **CTA:** LEARN_MORE

## History & intent
_(Shared Owner Market history; this ad is the **Varsity Lakes** targeting of the FORM campaign `120252423820580134`.)_

**Why we created it**
- Owner Market started 2026-08-26 as a geofenced carousel telling homeowners the "national-turn-vs-Gold-Coast-holding" story with their own suburb named, so they'd search their address and open their off-market analysis (a Lead). Broad + Advantage targeting, one ad set per suburb so geofence/landing/creative all match (learnings #7 OFFSITE_CONVERSIONS, #8 broad).
- This FORM arm was built the same day as an A/B alternative: a native in-app Instant Form that requests the address **in-form** and SMS-es the analysis link — betting that removing the page-load + on-site typing step captures more real addresses despite the prior 2026-07-28 "address-in-form friction" finding, because the value exchange (their own home's analysis) is strong. SMS is opt-in (form consent + STOP).

**What changed (pivots)**
- Carousel objective pivot: rebuilt from Lead-optimized → TRAFFIC / LANDING_PAGE_VIEWS, and API radius pins → Meta NEIGHBORHOOD targeting (cleaner per-suburb, no radius bleed).
- Creative — eyebrow: card 01 hook changed from generic "The national picture" to "**{Suburb} Analysis**"; then refreshed again to a full-width high-contrast black "**{SUBURB} ANALYSIS**" ledger band (Will picked version A of 4 mocks) for in-feed legibility.
- Creative — CTA: shorter benefit-led closing line ("see where your home sits—and the four market signals") + **LEARN_MORE** button (GET_STARTED isn't in Meta's carousel enum).
- Website-leadpage detour + reversal (2026-08-28): briefly switched to an on-site `/find` two-step capture (address → name+phone) optimized on the pixel Lead, then **reversed the same day** back to these autofill Instant Forms — the `/find` gate bled ~83% of address-enterers (PostHog: 101 landed → 7 entered address → 1 completed), and the Lead pixel fired only at the abandoned step so Meta saw ~0 conversions. Autofill Instant Forms fix both the capture loss and the optimisation starvation, and are attributed natively by Meta.
- Added email (v2 Instant Forms, 2026-08-28): Meta forms are immutable once they have leads, so email required new v2 forms + repointed creatives. The analysis link is now delivered by **both SMS (JustCall) and email**.

**What we're looking for now**
- Cost per **contactable** lead (every lead now carries name + phone + email vs the old contactless website captures).
- Meta "Results" actually populating (LEAD_GENERATION) and form open→submit rate.
- Fulfilment delivery + the `unresolved`-address count.
- Downstream lead **quality/intent** before scaling — autofill lowers friction, so watch quality doesn't drop.

## Notes / hypothesis / performance
_(add observations, what this ad is testing, results)_
