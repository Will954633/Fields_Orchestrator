# Carousel Lead v1 — C (florabella) → Buyer Brief v3 form

_Auto-generated 2026-08-29 from the Meta Ads API. Edit freely — notes below are yours._

| | |
|---|---|
| **Ad ID** | `120251749295410134` |
| **Status** | ACTIVE |
| **Created** | 2026-07-27T19:27 |

## Campaign
- **Name:** Leads: Buyer Brief — Carousel (florabella) v1
- **ID:** `120251749294700134`
- **Objective:** OUTCOME_LEADS

## Ad set
- **Name:** Carousel Lead — florabella — GC 25mi — A$15/day
- **ID:** `120251749294920134`
- **Daily budget:** $15.00/day
- **Optimization:** LEAD_GENERATION
- **Targeting:** Varsity Lakes, Robina, Burleigh Waters · age 25-65

## Creative / destination
- **Type:** SHARE
- **Destination:** `http://fb.me/`
- **CTA:** SIGN_UP

## History & intent

**Why we created it (2026-07-27)**
- The florabella carousel already drove strong, cheap clicks as a *traffic* ad (CTR 2.4-3.8%, CPC $0.19-0.48). This test wraps the SAME cards in a Lead objective (instant form) to see whether people will enter contactable name/email/phone off a carousel — before building SMS-link fulfilment.
- Isolated one variable vs existing single-image Buyer Brief lead ads (which ran CPC $0.98-1.94): carousel creative instead of single image, on a Lead objective.
- Reused the live Buyer Brief v3 form (Friday email fulfilment already worked) so there was no broken promise while SMS + deep-link pre-fill were deferred per Will. Attribution by ad_name/campaign via fb-lead-puller.
- Created PAUSED, then enabled same day at A$15/day, core-suburb targeting (Robina/Varsity Lakes/Burleigh Waters).

**What changed (pivots)**
- **2026-07-27 — dedicated copy.** The reused form copy sold the wrong product (weekly "5 Property Friday" email shortlist). Swapped in dedicated Option A copy built on independence/objectivity ("the analysis the listing won't give you"), matching the carousel's real product: published editorial analysis on /for-sale-v3. A NEW dedicated form was created so the shared Buyer Brief v3 form kept its real 5-Property-Friday product.
- **2026-08-18 — reframed as a 4th arm / buyer door to seller acquisition.** Will's call: a lead who owns a Gold Coast home AND is looking to buy is selling-to-buy, therefore a seller. On that reading the carousel produced 2 seller leads for $51.00 = $25.50 each — a second, cheaper acquisition door to the same person. Kept OUTSIDE the 3-arm creative test (it changes creative + format + form + product at once, shares no denominator). Also fixed adset geo from location_types ['home','recent'] to home-only (Gold Coast "recent" = tourists).
- **2026-08-29 — lead reclassified buyer, not seller.** A real lead (Sharon Lansley) fired a "New SELLER lead" alert, but she'd browsed for-sale listings and answered "not selling" on the on-page ladder. Root cause: the two "Independent Listing Analysis (carousel)" forms sat in SELLER_FORM_IDS despite the buyer campaign feeding /for-sale-v3. Fix removed them and routed all six homes-for-sale forms to a dedicated buyer notification ("🏠 New buyer lead — wants for-sale listings"). Also fixed alerts to render the exact ad name.

**What we're looking for now**
- Form-fill viability: whether people will submit contact details (name/email/phone) off a carousel creative on a Lead objective, at a good cost per lead (vs the ~$3.77 CPL single-image Buyer Brief baseline).
- Contactable, servable buyer leads from the core southern-GC suburbs — treated as buyers (wanting for-sale listings), with owns-a-GC-home answers flagged as potential future sellers (Will's inference, not instrumented: no address captured, so occupancy/seller-intent/came-to-market cannot fire).

## Notes / hypothesis / performance
_(add observations, what this ad is testing, results)_
